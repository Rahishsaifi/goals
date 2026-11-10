from __future__ import annotations

from dataclasses import dataclass, field

from app.goals_localization.language_config import TECHNICAL_FIELDS
from app.services.goals_localization.csv_reader import GoalSourceRecord
from app.services.goals_localization.excel_reader import TemplateRecord


@dataclass
class ReconciliationIssue:
    code: str
    severity: str
    message: str
    record_key: str | None = None


@dataclass
class ReconciledPair:
    source: GoalSourceRecord
    template: TemplateRecord


@dataclass
class ReconciliationResult:
    pairs: list[ReconciledPair] = field(default_factory=list)
    issues: list[ReconciliationIssue] = field(default_factory=list)
    unmatched_source: list[str] = field(default_factory=list)
    unmatched_target: list[str] = field(default_factory=list)

    @property
    def is_blocking(self) -> bool:
        return any(item.severity == "HIGH" for item in self.issues)


def reconcile(
    sources: list[GoalSourceRecord], templates: list[TemplateRecord]
) -> ReconciliationResult:
    result = ReconciliationResult()
    source_by_key = {item.record_key: item for item in sources}
    template_by_key = {item.record_key: item for item in templates}

    if len(source_by_key) != len(sources):
        result.issues.append(
            ReconciliationIssue(
                code="DUPLICATE_SOURCE_KEY",
                severity="HIGH",
                message="Source CSV has ambiguous duplicate keys after normalization.",
            )
        )
    if len(template_by_key) != len(templates):
        result.issues.append(
            ReconciliationIssue(
                code="DUPLICATE_TARGET_KEY",
                severity="HIGH",
                message="Target workbook has ambiguous duplicate keys.",
            )
        )

    for key, source in source_by_key.items():
        template = template_by_key.get(key)
        if template is None:
            result.unmatched_source.append(key)
            result.issues.append(
                ReconciliationIssue(
                    code="MISSING_TARGET_RECORD",
                    severity="HIGH",
                    message=f"No target row for source key '{key}'.",
                    record_key=key,
                )
            )
            continue
        for field_name in TECHNICAL_FIELDS:
            src_val = source.technical.get(field_name, "")
            tgt_val = template.technical.get(field_name, "")
            if src_val and not tgt_val:
                result.issues.append(
                    ReconciliationIssue(
                        code="MISSING_TECHNICAL_FIELD",
                        severity="HIGH",
                        message=f"{field_name} missing in target for '{key}'.",
                        record_key=key,
                    )
                )
            elif src_val and tgt_val and src_val != tgt_val:
                result.issues.append(
                    ReconciliationIssue(
                        code="TECHNICAL_FIELD_MISMATCH",
                        severity="HIGH",
                        message=(
                            f"{field_name} mismatch for '{key}': "
                            f"source='{src_val}' target='{tgt_val}'."
                        ),
                        record_key=key,
                    )
                )
        result.pairs.append(ReconciledPair(source=source, template=template))

    for key in template_by_key:
        if key not in source_by_key:
            result.unmatched_target.append(key)
            result.issues.append(
                ReconciliationIssue(
                    code="EXTRA_TARGET_RECORD",
                    severity="HIGH",
                    message=f"Target has extra record '{key}' not present in English source.",
                    record_key=key,
                )
            )

    if result.unmatched_source or result.unmatched_target:
        # Ambiguous mapping — stop rather than guess by row order.
        result.issues.append(
            ReconciliationIssue(
                code="RECONCILIATION_AMBIGUOUS",
                severity="HIGH",
                message="Record mapping incomplete; refusing to guess by row order.",
            )
        )
    return result
