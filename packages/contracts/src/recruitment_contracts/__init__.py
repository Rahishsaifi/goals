"""Shared API contracts. No I/O and no tenant trust decisions."""

from recruitment_contracts.errors import ErrorBody, ErrorResponse
from recruitment_contracts.health import HealthResponse

__all__ = ["ErrorBody", "ErrorResponse", "HealthResponse"]
