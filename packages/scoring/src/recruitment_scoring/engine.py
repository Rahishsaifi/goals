from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from recruitment_scoring import SCORING_ALGORITHM_VERSION, weighted_contribution

EvidenceStatus = Literal["satisfied", "not_satisfied", "unknown"]


@dataclass(frozen=True)
class CriterionInput:
    key: str
    weight: Decimal
    mandatory: bool
    score: Decimal
    status: EvidenceStatus


@dataclass(frozen=True)
class ScoreResult:
    overall_score: Decimal
    mandatory_status: EvidenceStatus
    review_required: bool
    contributions: list[dict[str, object]]
    scoring_algorithm_version: str


def validate_weights(criteria: list[dict[str, object]]) -> None:
    total = sum(Decimal(str(c.get("weight", 0))) for c in criteria)
    if any(Decimal(str(c.get("weight", 0))) < 0 for c in criteria):
        raise ValueError("weights must be non-negative")
    if total != Decimal("100"):
        raise ValueError(f"weights must sum to 100, got {total}")


def score_candidate(criteria: list[CriterionInput]) -> ScoreResult:
    contributions: list[dict[str, object]] = []
    overall = Decimal("0")
    mandatory_statuses = [c.status for c in criteria if c.mandatory]
    for criterion in criteria:
        contribution = weighted_contribution(criterion.weight, criterion.score)
        overall += contribution
        contributions.append(
            {
                "key": criterion.key,
                "weight": str(criterion.weight),
                "score": str(criterion.score),
                "contribution": str(contribution),
                "status": criterion.status,
                "mandatory": criterion.mandatory,
            }
        )
    if not mandatory_statuses:
        mandatory_status: EvidenceStatus = "satisfied"
    elif any(status == "not_satisfied" for status in mandatory_statuses):
        mandatory_status = "not_satisfied"
    elif any(status == "unknown" for status in mandatory_statuses):
        mandatory_status = "unknown"
    else:
        mandatory_status = "satisfied"
    review_required = mandatory_status == "unknown" or any(
        c.status == "unknown" for c in criteria
    )
    return ScoreResult(
        overall_score=overall,
        mandatory_status=mandatory_status,
        review_required=review_required,
        contributions=contributions,
        scoring_algorithm_version=SCORING_ALGORITHM_VERSION,
    )
