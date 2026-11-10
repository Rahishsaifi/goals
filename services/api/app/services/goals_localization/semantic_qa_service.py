from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.integrations.foundry_provider import FoundryModelProvider, FoundryProviderError

logger = logging.getLogger(__name__)
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "goals_localization" / "prompts" / "semantic_translation_qa.txt"
_CORRECTION_PATH = Path(__file__).resolve().parents[2] / "goals_localization" / "prompts" / "translation_correction.txt"


class QAIssue(BaseModel):
    type: str
    severity: Literal["HIGH", "MEDIUM", "LOW"]
    explanation: str


class FieldQA(BaseModel):
    status: Literal["PASS", "FAIL"]
    issues: list[QAIssue] = Field(default_factory=list)


class SemanticQAResult(BaseModel):
    record_id: str
    overall_status: Literal["PASS", "FAIL"]
    fields: dict[str, FieldQA]
    recommendation: Literal["KEEP", "CORRECT", "HUMAN_REVIEW"]


class CorrectionResult(BaseModel):
    field: Literal["goal", "description", "kra"]
    corrected_text: str
    notes: str = ""


def _load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class SemanticQAService:
    def __init__(self, provider: FoundryModelProvider) -> None:
        self.provider = provider
        self.input_tokens = 0
        self.output_tokens = 0

    def assess_record(
        self,
        *,
        record_id: str,
        target_language: str,
        source_goal: str,
        source_description: str,
        source_kra: str,
        translated_goal: str,
        translated_description: str,
        translated_kra: str,
    ) -> SemanticQAResult:
        system = _load_prompt(_PROMPT_PATH)
        user = json.dumps(
            {
                "record_id": record_id,
                "target_language": target_language,
                "source": {
                    "goal": source_goal,
                    "description": source_description,
                    "kra": source_kra,
                },
                "translation": {
                    "goal": translated_goal,
                    "description": translated_description,
                    "kra": translated_kra,
                },
            },
            ensure_ascii=False,
        )
        payload = self.provider._chat_json(system=system, user=user)
        usage = payload["usage"]
        self.input_tokens += usage.input_tokens or 0
        self.output_tokens += usage.output_tokens or 0
        raw = payload["json"]
        if "record_id" not in raw:
            raw["record_id"] = record_id
        return SemanticQAResult.model_validate(raw)

    def correct_field(
        self,
        *,
        field: Literal["goal", "description", "kra"],
        target_language: str,
        source_text: str,
        failed_translation: str,
        issues: list[dict[str, object]],
        preserve_terms: list[str],
    ) -> CorrectionResult:
        system = _load_prompt(_CORRECTION_PATH)
        user = json.dumps(
            {
                "field": field,
                "target_language": target_language,
                "source_text": source_text,
                "failed_translation": failed_translation,
                "issues": issues,
                "preserve_terms": preserve_terms,
            },
            ensure_ascii=False,
        )
        payload = self.provider._chat_json(system=system, user=user)
        usage = payload["usage"]
        self.input_tokens += usage.input_tokens or 0
        self.output_tokens += usage.output_tokens or 0
        raw = payload["json"]
        raw["field"] = field
        return CorrectionResult.model_validate(raw)


def build_semantic_qa_service() -> SemanticQAService:
    try:
        provider = FoundryModelProvider()
    except FoundryProviderError as exc:
        raise FoundryProviderError(
            f"Semantic QA requires Foundry/Azure OpenAI configuration: {exc}"
        ) from exc
    return SemanticQAService(provider)
