from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any


def build_qa_report(
    *,
    job_id: str,
    target_language: str,
    production_ready: bool,
    summary: dict[str, Any],
    gate_checks: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    stages: dict[str, Any],
) -> bytes:
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "job_id": job_id,
        "target_language": target_language,
        "production_ready": production_ready,
        "label": "PRODUCTION READY" if production_ready else "NOT PRODUCTION READY",
        "summary": summary,
        "hard_gate": gate_checks,
        "stages": stages,
        "issues": issues,
        "disclaimer": (
            "SAP SuccessFactors import readiness requires production_ready=true. "
            "A generated workbook alone is not proof of readiness."
        ),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
