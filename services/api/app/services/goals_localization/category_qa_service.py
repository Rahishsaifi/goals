from __future__ import annotations

from dataclasses import dataclass, field

from app.services.goals_localization.numeric_validator import compare_numeric_fields


SPECIAL_CATEGORIES = frozenset({"Hotel Revenue Growth", "Operational Productivity"})


@dataclass
class CategoryIssue:
    category: str
    record_key: str
    code: str
    message: str


@dataclass
class CategoryQAResult:
    issues: list[CategoryIssue] = field(default_factory=list)

    @property
    def hotel_revenue_pass(self) -> bool:
        return not any(i.category == "Hotel Revenue Growth" for i in self.issues)

    @property
    def operational_productivity_pass(self) -> bool:
        return not any(i.category == "Operational Productivity" for i in self.issues)


def validate_special_categories(
    records: list[dict[str, str]],
) -> CategoryQAResult:
    """records keys: record_key, category, source_goal/description/kra, translated_*"""
    result = CategoryQAResult()
    for row in records:
        category = (row.get("category") or "").strip()
        if category not in SPECIAL_CATEGORIES:
            continue
        for field in ("goal", "description", "kra"):
            source = row.get(f"source_{field}", "")
            translated = row.get(f"translated_{field}", "")
            if source and not translated:
                result.issues.append(
                    CategoryIssue(
                        category=category,
                        record_key=row["record_key"],
                        code="BLANK_SPECIAL_CATEGORY_FIELD",
                        message=f"{category}: translated {field} is blank while English has content.",
                    )
                )
            for issue in compare_numeric_fields(source, translated):
                result.issues.append(
                    CategoryIssue(
                        category=category,
                        record_key=row["record_key"],
                        code=issue.kind,
                        message=f"{category}: {issue.message}",
                    )
                )
    return result
