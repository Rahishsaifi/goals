from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.integrations.foundry_provider import FoundryModelProvider, FoundryProviderError

logger = logging.getLogger(__name__)
_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "goals_localization" / "prompts"
_PROMPT_PATH = _PROMPTS_DIR / "semantic_translation_qa.txt"
_CORRECTION_PATH = _PROMPTS_DIR / "translation_correction.txt"
_REVISION_PATH = _PROMPTS_DIR / "semantic_revision.txt"


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


class RevisedField(BaseModel):
    text: str
    changed: bool = False
    reason: str = ""


class RecordRevision(BaseModel):
    goal: RevisedField
    description: RevisedField
    kra: RevisedField


def _load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class SemanticQAService:
    def __init__(
        self, provider: FoundryModelProvider, gate: FoundryRateGate | None = None
    ) -> None:
        self.provider = provider
        self.gate = gate
        self.input_tokens = 0
        self.output_tokens = 0
        self._usage_lock = threading.Lock()

    def _record_usage(self, usage: object) -> None:
        with self._usage_lock:
            self.input_tokens += getattr(usage, "input_tokens", None) or 0
            self.output_tokens += getattr(usage, "output_tokens", None) or 0

    def _chat(self, *, system: str, user: str, max_attempts: int = 5) -> dict[str, object]:
        """Foundry call with a shared rate limit. Safe to call from worker threads."""
        # Rough estimate: ~4 characters per token for the prompt, plus the reply.
        estimate = (len(system) + len(user)) // 4 + 600
        attempt = 0
        while True:
            attempt += 1
            if self.gate is not None:
                self.gate.acquire(estimate)
            try:
                payload = self.provider._chat_json(system=system, user=user)
            except FoundryProviderError as exc:
                if attempt >= max_attempts:
                    raise
                delay = min(60.0, 5.0 * 2 ** (attempt - 1))
                if "429" in str(exc) and self.gate is not None:
                    self.gate.pause(delay)
                logger.warning(
                    "foundry_retry attempt=%s/%s delay=%.0fs error=%s",
                    attempt,
                    max_attempts,
                    delay,
                    str(exc)[:200],
                )
                time.sleep(delay)
                continue
            self._record_usage(payload["usage"])
            return payload

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

    def revise_record(
        self,
        *,
        target_language: str,
        source_goal: str,
        source_description: str,
        source_kra: str,
        translated_goal: str,
        translated_description: str,
        translated_kra: str,
        preserve_terms: list[str],
        system_prompt: str | None = None,
    ) -> RecordRevision:
        """Ask Foundry to repair meaning. Unchanged fields come back as written."""
        originals = {
            "goal": translated_goal,
            "description": translated_description,
            "kra": translated_kra,
        }
        system = (system_prompt or "").strip() or _load_prompt(_REVISION_PATH)
        user = json.dumps(
            {
                "target_language": target_language,
                "preserve_terms": preserve_terms,
                "source": {
                    "goal": source_goal,
                    "description": source_description,
                    "kra": source_kra,
                },
                "translation": originals,
            },
            ensure_ascii=False,
        )
        payload = self._chat(system=system, user=user)
        return normalize_revision(payload["json"], originals)


class FoundryRateGate:
    """Shared tokens-per-minute ceiling and 429 pause for parallel Foundry requests."""

    def __init__(self, tokens_per_minute: int) -> None:
        self.limit = max(1000, tokens_per_minute)
        self._lock = threading.Lock()
        self._sent: deque[tuple[float, int]] = deque()
        self._paused_until = 0.0

    def acquire(self, tokens: int) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._sent and now - self._sent[0][0] >= 60:
                    self._sent.popleft()
                wait = self._paused_until - now
                if wait <= 0:
                    used = sum(count for _, count in self._sent)
                    if not self._sent or used + tokens <= self.limit:
                        self._sent.append((now, tokens))
                        return
                    wait = 60 - (now - self._sent[0][0])
            time.sleep(min(max(wait, 0.05), 5.0))

    def pause(self, seconds: float) -> None:
        with self._lock:
            self._paused_until = max(self._paused_until, time.monotonic() + seconds)


def normalize_revision(raw: object, originals: dict[str, str]) -> RecordRevision:
    """Keep the translator text when Foundry omits a field or returns a blank."""
    payload = raw if isinstance(raw, dict) else {}
    normalized: dict[str, dict[str, object]] = {}
    for field, original in originals.items():
        item = payload.get(field, {})
        if isinstance(item, str):
            item = {"text": item, "changed": item != original}
        if not isinstance(item, dict):
            item = {}
        text = str(item.get("text") or original)
        if original.strip() and not text.strip():
            text = original
        changed = bool(item.get("changed")) and text != original
        normalized[field] = {
            "text": text,
            "changed": changed,
            "reason": str(item.get("reason") or "") if changed else "",
        }
    return RecordRevision.model_validate(normalized)


def build_semantic_qa_service(gate: FoundryRateGate | None = None) -> SemanticQAService:
    try:
        provider = FoundryModelProvider()
    except FoundryProviderError as exc:
        raise FoundryProviderError(
            f"Semantic QA requires Foundry/Azure OpenAI configuration: {exc}"
        ) from exc
    return SemanticQAService(provider, gate)
