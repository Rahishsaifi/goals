from decimal import Decimal

import pytest
from recruitment_scoring import weighted_contribution


def test_weighted_contribution_uses_decimal_division() -> None:
    assert weighted_contribution(Decimal("30"), Decimal("80")) == Decimal("24")


def test_weighted_contribution_rejects_negative_weight() -> None:
    with pytest.raises(ValueError):
        weighted_contribution(Decimal("-1"), Decimal("10"))
