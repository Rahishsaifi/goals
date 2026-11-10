from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GateCheck:
    name: str
    required: str
    actual: str
    passed: bool


@dataclass
class HardGateResult:
    production_ready: bool
    checks: list[GateCheck] = field(default_factory=list)


def evaluate_hard_gate(summary: dict[str, object]) -> HardGateResult:
    checks: list[GateCheck] = []

    def add(name: str, required: str, actual: object, passed: bool) -> None:
        checks.append(GateCheck(name=name, required=required, actual=str(actual), passed=passed))

    source_count = int(summary.get("source_record_count") or 0)
    output_count = int(summary.get("output_record_count") or 0)
    unmatched = int(summary.get("unmatched_records") or 0)
    duplicates = int(summary.get("duplicate_records") or 0)
    missing_tech = int(summary.get("missing_technical_fields") or 0)
    blank_goal = int(summary.get("blank_goal_violations") or 0)
    blank_desc = int(summary.get("blank_description_violations") or 0)
    blank_kra = int(summary.get("blank_kra_violations") or 0)
    numeric = int(summary.get("numeric_discrepancies") or 0)
    percent = int(summary.get("percentage_discrepancies") or 0)
    quarters = int(summary.get("quarter_discrepancies") or 0)
    dates = int(summary.get("date_discrepancies") or 0)
    unresolved_high = int(summary.get("unresolved_high_severity_issues") or 0)
    unresolved_terms = int(summary.get("unresolved_terminology_issues") or 0)
    hotel_pass = bool(summary.get("hotel_revenue_growth_qa_pass"))
    ops_pass = bool(summary.get("operational_productivity_qa_pass"))
    workbook_ok = bool(summary.get("workbook_post_save_integrity"))
    unresolved_english = int(summary.get("unresolved_untranslated_english") or 0)

    add("Source record count", "reported", source_count, source_count > 0)
    add("Output record count", "equal to source", output_count, output_count == source_count and source_count > 0)
    add("Unmatched records", "0", unmatched, unmatched == 0)
    add("Duplicate records", "0", duplicates, duplicates == 0)
    add("Missing technical fields", "0 where English has value", missing_tech, missing_tech == 0)
    add("Blank Goal", "0 unless source blank", blank_goal, blank_goal == 0)
    add("Blank Description", "0 unless source blank", blank_desc, blank_desc == 0)
    add("Blank KRA", "0 unless source blank", blank_kra, blank_kra == 0)
    add("Numeric discrepancies", "0", numeric, numeric == 0)
    add("Percentage discrepancies", "0", percent, percent == 0)
    add("Quarter discrepancies", "0", quarters, quarters == 0)
    add("Date/deadline discrepancies", "0", dates, dates == 0)
    add("Unresolved high-severity semantic issues", "0", unresolved_high, unresolved_high == 0)
    add("Unresolved material terminology issues", "0", unresolved_terms, unresolved_terms == 0)
    add("Hotel Revenue Growth QA", "PASS", hotel_pass, hotel_pass)
    add("Operational Productivity QA", "PASS", ops_pass, ops_pass)
    add("Workbook post-save integrity", "PASS", workbook_ok, workbook_ok)
    add("Unresolved untranslated English", "0", unresolved_english, unresolved_english == 0)

    return HardGateResult(production_ready=all(item.passed for item in checks), checks=checks)
