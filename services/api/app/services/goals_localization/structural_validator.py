from __future__ import annotations

from dataclasses import dataclass, field

from app.services.goals_localization.csv_reader import GoalSourceRecord
from app.services.goals_localization.excel_reader import TemplateWorkbookInfo
from app.services.goals_localization.source_reconciliation import ReconciliationResult


@dataclass
class StructuralIssue:
    code: str
    severity: str
    message: str


@dataclass
class StructuralValidationResult:
    issues: list[StructuralIssue] = field(default_factory=list)
    source_count: int = 0
    target_count: int = 0

    @property
    def ok(self) -> bool:
        return not any(item.severity == "HIGH" for item in self.issues)


def validate_structure(
    *,
    sources: list[GoalSourceRecord],
    template: TemplateWorkbookInfo,
    reconciliation: ReconciliationResult,
) -> StructuralValidationResult:
    result = StructuralValidationResult(
        source_count=len(sources),
        target_count=len(template.records),
    )
    if result.source_count != result.target_count:
        result.issues.append(
            StructuralIssue(
                code="ROW_COUNT_MISMATCH",
                severity="HIGH",
                message=f"Source rows={result.source_count} target rows={result.target_count}.",
            )
        )
    for issue in reconciliation.issues:
        result.issues.append(
            StructuralIssue(code=issue.code, severity=issue.severity, message=issue.message)
        )
    required_cols = {"Goal", "Description", "KRA"}
    missing = required_cols - set(template.column_index)
    if missing:
        result.issues.append(
            StructuralIssue(
                code="COLUMN_MISSING",
                severity="HIGH",
                message=f"Template missing columns: {', '.join(sorted(missing))}",
            )
        )
    return result
