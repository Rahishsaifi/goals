"""Deterministic scoring helpers.

Weighted math lives here. Model output must not calculate the fit score.
"""

from decimal import Decimal

SCORING_ALGORITHM_VERSION = "1"

_HUNDRED = Decimal("100")


def weighted_contribution(weight: Decimal, criterion_score: Decimal) -> Decimal:
    """Return weight * score / 100 using Decimal arithmetic."""
    if weight < 0 or criterion_score < 0:
        raise ValueError("weight and criterion_score must be non-negative")
    return (weight * criterion_score) / _HUNDRED
