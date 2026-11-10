from decimal import Decimal

import pytest
from recruitment_scoring.engine import CriterionInput, score_candidate, validate_weights


def test_validate_weights_requires_exact_hundred() -> None:
    with pytest.raises(ValueError):
        validate_weights([{"weight": 40}, {"weight": 40}])


def test_missing_evidence_is_unknown_not_failure() -> None:
    result = score_candidate(
        [
            CriterionInput(
                key="technical_skills",
                weight=Decimal("100"),
                mandatory=True,
                score=Decimal("0"),
                status="unknown",
            )
        ]
    )
    assert result.mandatory_status == "unknown"
    assert result.review_required is True
    assert result.overall_score == Decimal("0")


def test_deterministic_weighted_sum() -> None:
    result = score_candidate(
        [
            CriterionInput(
                key="a",
                weight=Decimal("30"),
                mandatory=False,
                score=Decimal("100"),
                status="satisfied",
            ),
            CriterionInput(
                key="b",
                weight=Decimal("70"),
                mandatory=False,
                score=Decimal("50"),
                status="satisfied",
            ),
        ]
    )
    assert result.overall_score == Decimal("65")
