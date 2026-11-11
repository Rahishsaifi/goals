from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Literal

import httpx

from app.integrations.model_provider import (
    CriterionAssessment,
    ExtractedProfile,
    ProviderResult,
    UsageTelemetry,
)

logger = logging.getLogger(__name__)


def _weight(criterion: dict[str, object]) -> float:
    value = criterion.get("weight")
    return float(value) if isinstance(value, (int, float)) else 0.0


class FoundryProviderError(RuntimeError):
    """Raised when a live Foundry/OpenAI call fails. Never fall back to mock."""


class FoundryModelProvider:
    """Azure OpenAI chat deployments (Foundry-compatible endpoint)."""

    name = "foundry"

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        api_key: str | None = None,
        deployment: str | None = None,
        api_version: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        from app.core.config import get_settings

        settings = get_settings()
        self.endpoint = (
            endpoint
            or settings.azure_openai_endpoint
            or os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        ).rstrip("/")
        self.api_key = (
            api_key
            or settings.azure_openai_api_key
            or os.environ.get("AZURE_OPENAI_API_KEY", "")
            or ""
        )
        self.deployment = (
            deployment
            or os.environ.get("AZURE_OPENAI_DEPLOYMENT")
            or settings.azure_openai_deployment
        )
        self.api_version = (
            api_version
            or os.environ.get("AZURE_OPENAI_API_VERSION")
            or settings.azure_openai_api_version
        )
        self.timeout_seconds = timeout_seconds
        if not self.endpoint or not self.api_key:
            raise FoundryProviderError(
                "Foundry provider requires AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY."
            )

    def extract_resume_profile(self, text: str) -> ProviderResult[ExtractedProfile]:
        from app.parsers.contact import extract_contact_fields

        payload = self._chat_json(
            system=(
                "Extract structured resume facts. Return JSON only with keys: "
                "full_name (string|null), email (string|null), phone (string|null), "
                "location (string|null), skills (string[]), job_titles (string[]), "
                "employers (string[]), qualifications (string[]), summary (string), "
                "evidence_passages (string[]). "
                "evidence_passages must be short verbatim quotes that support skills, "
                "experience, domain work, and qualifications (up to 8). "
                "If evidence is missing, use null/empty arrays/strings. Do not invent employers."
            ),
            user=text[:12000],
        )
        value = ExtractedProfile.model_validate(payload["json"])
        contact = extract_contact_fields(text)
        if not value.full_name:
            value.full_name = contact.get("full_name")
        if not value.email:
            value.email = contact.get("email")
        if not value.phone:
            value.phone = contact.get("phone")
        if not value.location:
            value.location = contact.get("location")
        return ProviderResult(value=value, usage=payload["usage"])

    def extract_jd_requirements(self, text: str) -> ProviderResult[list[dict[str, object]]]:
        payload = self._chat_json(
            system=(
                "Extract hiring criteria from a job description. Return JSON only: "
                '{"criteria":[{"key":str,"display_name":str,"weight":number,"mandatory":bool,'
                '"severity":"mandatory|preferred|informational","description":str}]}. '
                "Weights must be non-negative and sum to exactly 100. Prefer 4-8 criteria."
            ),
            user=text[:12000],
        )
        raw = payload["json"]
        criteria = raw.get("criteria", raw if isinstance(raw, list) else [])
        if not isinstance(criteria, list) or not criteria:
            raise FoundryProviderError("Foundry JD extraction returned no criteria.")
        normalized: list[dict[str, object]] = []
        for item in criteria:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "key": str(item.get("key", "criterion")),
                    "display_name": str(item.get("display_name", item.get("key", "Criterion"))),
                    "weight": float(item.get("weight", 0)),
                    "mandatory": bool(item.get("mandatory", False)),
                    "severity": str(item.get("severity", "preferred")),
                    "description": str(item.get("description", "")),
                }
            )
        total = sum(_weight(c) for c in normalized)
        if abs(total - 100.0) > 0.01:
            # Keep deterministic scoring valid without inventing criteria content.
            scale = 100.0 / total if total > 0 else 0.0
            if scale <= 0:
                raise FoundryProviderError("Foundry JD weights were invalid.")
            for criterion in normalized:
                criterion["weight"] = round(_weight(criterion) * scale, 4)
            drift = 100.0 - sum(_weight(c) for c in normalized)
            normalized[0]["weight"] = round(_weight(normalized[0]) + drift, 4)
        return ProviderResult(value=normalized, usage=payload["usage"])

    def assess_criteria_from_profile(
        self, *, criteria: list[dict[str, object]], profile: dict[str, object]
    ) -> ProviderResult[list[CriterionAssessment]]:
        compact_criteria = [
            {
                "key": str(item.get("key", "unknown")),
                "display_name": str(item.get("display_name") or item.get("key") or "Criterion"),
                "description": str(item.get("description") or ""),
                "mandatory": bool(item.get("mandatory", False)),
            }
            for item in criteria
        ]
        compact_profile = _compact_profile(profile)
        payload = self._chat_json(
            system=(
                "Assess all hiring criteria against a structured resume profile only. "
                "Do not invent employers, skills, or qualifications that are absent. "
                "Return JSON only: "
                '{"assessments":[{"criterion_key":str,"score":0-100,'
                '"status":"satisfied|not_satisfied|unknown","passage":str|null,'
                '"page_number":number|null}]}. '
                "Include exactly one assessment per criterion key. "
                "Use unknown when the profile lacks enough evidence. "
                "passage must be a short quote from summary/evidence_passages or null."
            ),
            user=json.dumps(
                {"criteria": compact_criteria, "profile": compact_profile},
                ensure_ascii=False,
            ),
        )
        body = payload["json"]
        raw_items = body.get("assessments", body if isinstance(body, list) else [])
        by_key: dict[str, CriterionAssessment] = {}
        if isinstance(raw_items, list):
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("criterion_key", "unknown"))
                status_raw = str(item.get("status", "unknown"))
                status: Literal["satisfied", "not_satisfied", "unknown"]
                if status_raw in {"satisfied", "not_satisfied", "unknown"}:
                    status = status_raw  # type: ignore[assignment]
                else:
                    status = "unknown"
                try:
                    score = float(item.get("score", 0))
                except (TypeError, ValueError):
                    score = 0.0
                score = max(0.0, min(100.0, score))
                by_key[key] = CriterionAssessment(
                    criterion_key=key,
                    score=score,
                    status=status,
                    passage=item.get("passage") if item.get("passage") is not None else None,
                    page_number=_as_optional_int(item.get("page_number")),
                )
        assessments: list[CriterionAssessment] = []
        for criterion in criteria:
            key = str(criterion.get("key", "unknown"))
            assessments.append(
                by_key.get(
                    key,
                    CriterionAssessment(
                        criterion_key=key,
                        score=0.0,
                        status="unknown",
                        passage=None,
                        page_number=None,
                    ),
                )
            )
        return ProviderResult(value=assessments, usage=payload["usage"])

    def _chat_json(self, *, system: str, user: str) -> dict[str, Any]:
        url = (
            f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions"
            f"?api-version={self.api_version}"
        )
        request_body = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        max_attempts = 3
        response: httpx.Response | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                response = httpx.post(
                    url,
                    headers={"api-key": self.api_key, "content-type": "application/json"},
                    json=request_body,
                    timeout=self.timeout_seconds,
                )
            except httpx.HTTPError as exc:
                raise FoundryProviderError(f"Foundry request failed: {exc}") from exc
            if response.status_code != 429:
                break
            retry_after = response.headers.get("retry-after")
            try:
                # Cap waits so one job cannot block the worker queue for minutes.
                delay = min(float(retry_after) if retry_after else float(2**attempt), 2.0)
            except ValueError:
                delay = min(float(2**attempt), 2.0)
            logger.warning(
                "foundry_rate_limited attempt=%s/%s delay=%.1fs",
                attempt,
                max_attempts,
                delay,
            )
            if attempt == max_attempts:
                break
            time.sleep(delay)
        assert response is not None
        if response.status_code >= 400:
            raise FoundryProviderError(
                f"Foundry HTTP {response.status_code}: {response.text[:500]}"
            )
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise FoundryProviderError("Foundry response missing message content.") from exc
        parsed = _parse_json_object(content)
        usage_raw = data.get("usage") or {}
        usage = UsageTelemetry(
            input_tokens=_as_optional_int(usage_raw.get("prompt_tokens")),
            output_tokens=_as_optional_int(usage_raw.get("completion_tokens")),
            embedding_tokens=None,
            usage_available=bool(usage_raw),
            model_deployment=self.deployment,
            provider_request_id=response.headers.get("x-request-id"),
        )
        return {"json": parsed, "usage": usage}


def _compact_profile(profile: dict[str, object]) -> dict[str, object]:
    def as_str_list(value: object, *, limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        items: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                items.append(text[:240])
            if len(items) >= limit:
                break
        return items

    summary = str(profile.get("summary") or "")[:1500]
    passages = as_str_list(profile.get("evidence_passages"), limit=8)
    return {
        "full_name": profile.get("full_name"),
        "headline_location": profile.get("location"),
        "skills": as_str_list(profile.get("skills"), limit=40),
        "job_titles": as_str_list(profile.get("job_titles"), limit=20),
        "employers": as_str_list(profile.get("employers"), limit=20),
        "qualifications": as_str_list(profile.get("qualifications"), limit=20),
        "summary": summary,
        "evidence_passages": passages,
    }


def _parse_json_object(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not match:
            raise FoundryProviderError("Foundry returned non-JSON content.") from None
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise FoundryProviderError("Foundry JSON payload must be an object.")
    return parsed


def _as_optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
