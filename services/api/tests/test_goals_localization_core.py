from __future__ import annotations

import io

from openpyxl import Workbook

from app.goals_localization.language_config import list_languages, resolve_language, resolve_qa_mode
from app.services.goals_localization.csv_reader import read_english_csv
from app.services.goals_localization.excel_generator import (
    ExcelWriteRow,
    build_workbook_from_sources,
    reconstruct_workbook,
)
from app.services.goals_localization.excel_reader import read_template_workbook
from app.services.goals_localization.hard_gate import evaluate_hard_gate
from app.services.goals_localization.numeric_validator import compare_numeric_fields
from app.services.goals_localization.source_reconciliation import reconcile
from app.services.goals_localization.structural_validator import validate_structure
from app.services.goals_localization.terminology_protection import (
    protect_structural,
    protect_terminology,
    restore_terminology,
    verify_preserved_terms,
)
from app.services.goals_localization.translation_repair import (
    find_meaning_defects,
    repair_translation,
)
from app.services.goals_localization.untranslated_english import detect_residual_english


def _csv_bytes() -> bytes:
    return (
        b"GoalId,Goal,Description,KRA,JobLevelCode,LeaderOrNonLeader,FunctionalArea,JobFunctionCode,Category\n"
        b"G1,Grow revenue 10%,Increase ARR by 10% by Q4 2026,Revenue KRA,"
        b"L5,Leader,Sales,JF01,Hotel Revenue Growth\n"
        b"G2,Improve ops,Cut waste 5%,Ops KRA,L4,NonLeader,Ops,JF02,Operational Productivity\n"
    )


def _xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(
        [
            "GoalId",
            "Goal",
            "Description",
            "KRA",
            "JobLevelCode",
            "LeaderOrNonLeader",
            "FunctionalArea",
            "JobFunctionCode",
            "Category",
            "Code",
        ]
    )
    ws.append(
        ["G1", "old", "old", "old", "L5", "Leader", "Sales", "JF01", "Hotel Revenue Growth", "en"]
    )
    ws.append(
        [
            "G2", "old", "old", "old", "L4", "NonLeader", "Ops", "JF02",
            "Operational Productivity", "en",
        ]
    )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_language_config_centralized() -> None:
    langs = list_languages()
    assert [item["name"] for item in langs] == [
        "Simplified Chinese",
        "Japanese",
        "Dutch",
        "German",
        "European French",
        "European Spanish",
        "Latam Spanish",
        "Brazilian Portuguese",
        "Czech",
        "Polish",
        "Italian",
        "English UK",
        "Canadian French",
    ]
    assert resolve_language("zh").azure_translator_code == "zh-Hans"
    assert resolve_language("zh").sheet_code == "zh"
    assert resolve_language("es-latam").sheet_code == "es"
    assert resolve_language("fr-ca").azure_translator_code == "fr-ca"
    assert resolve_language("en-gb").translate is False
    assert resolve_language("en-gb").sheet_code == "en"
    try:
        resolve_language("en")
    except ValueError:
        pass
    else:
        raise AssertionError("English is the source language and must not be a target.")
    assert resolve_qa_mode(None) == "classic"
    assert resolve_qa_mode("foundry") == "foundry"


def test_structural_tokens_are_held_for_translation() -> None:
    source = "Grow 15% by Q4 2026 and close on 2026-03-31"
    protected = protect_structural(source)
    assert "Q4" not in protected.text
    assert "by " not in protected.text.lower()
    assert "15%" not in protected.text
    assert "2026" not in protected.text
    assert restore_terminology(protected.text, protected.mapping) == source


def test_by_quarter_is_repaired_in_chinese_and_german() -> None:
    source = (
        "1. By Q2, select a workflow. 2. By Q3, put it into use. "
        "3. By Q4, demonstrate improvement against the agreed baseline."
    )
    chinese = (
        "1. 通过Q2，选择一个工作流程。2. Q3，将它投入使用。"
        "3. 通过 Q4，展示改进与约定基线相符的改进。"
    )
    repaired = repair_translation(source, chinese, "zh-Hans")
    assert "通过" not in repaired
    assert repaired.startswith("1. 在Q2之前")
    assert "2. 在Q3之前" in repaired
    assert "3. 在Q4之前" in repaired
    assert find_meaning_defects(source, repaired, "zh-Hans") == []

    german = "1. Identifizieren Sie Q2 einen wiederkehrenden Schritt."
    german_source = "1. By Q2, identify a recurring step."
    fixed = repair_translation(german_source, german, "de")
    assert fixed.startswith("1. bis Q2 ")
    assert find_meaning_defects(german_source, fixed, "de") == []


def test_preserve_protects_allow_english_only_skips_residual_qa() -> None:
    """Preserve protects tokens. Allow English must not be protected or restored."""
    from app.services.goals_localization.glossary_store import GlossaryTerm, _snapshot

    snap = _snapshot(
        [
            GlossaryTerm(term="TripSource", action="preserve"),
            GlossaryTerm(term="Client Delivery Quality", action="allow"),
        ]
    )
    assert snap.preserve == ("TripSource",)
    assert "Client Delivery Quality" not in snap.preserve
    assert "TripSource" in snap.allow
    assert "Client Delivery Quality" in snap.allow

    source = "Improve TripSource and Client Delivery Quality across teams"
    protected = protect_terminology(source, terms=snap.preserve)
    assert "TripSource" not in protected.text
    assert "__KEEP_" in protected.text
    assert "Client Delivery Quality" in protected.text

    # Allow English phrase left in English is not flagged; other English phrases are.
    hits = detect_residual_english(
        field="goal",
        source=source,
        translated="Improve TripSource and Client Delivery Quality across teams",
        target_language="zh",
        allowlist=snap.allow,
    )
    assert all(hit.token != "Client Delivery Quality" for hit in hits)
    flagged = detect_residual_english(
        field="goal",
        source="Improve client program delivery across teams",
        translated="Improve client program delivery across teams",
        target_language="zh",
        allowlist=snap.allow,
    )
    assert flagged


def test_meaning_is_not_rewritten_by_a_fixed_phrase_list() -> None:
    source = "set priorities and clear ownership for simplifying a workflow"
    translated = "设定优先级并明确所有权，以简化工作流程。"
    assert repair_translation(source, translated, "zh-Hans") == translated


def test_adjacent_preserved_terms_keep_a_space() -> None:
    source = "Report M&E for Meetings & Events across Energy, Resources & Marine."
    translated = "报告Meetings & EventsM&E，范围是Energy, Resources & Marine。"
    repaired = repair_translation(
        source,
        translated,
        "zh-Hans",
        ("Energy, Resources & Marine", "Meetings & Events", "M&E"),
    )
    assert "Meetings & Events M&E" in repaired
    assert "EventsM&E" not in repaired


def test_preserved_term_is_not_glued_to_the_next_word() -> None:
    source = "Select EBITDA a recurring workflow."
    translated = "Einen wiederkehrenden Workflow EBITDAauswählen."
    repaired = repair_translation(source, translated, "de", ("EBITDA",))
    assert "EBITDA auswählen" in repaired
    assert "EBITDAauswählen" not in repaired


def test_shared_words_are_not_untranslated_english() -> None:
    hits = detect_residual_english(
        field="goal",
        source="Improve client program delivery",
        translated="Améliorer la prestation des programmes client",
        target_language="fr",
    )
    assert hits == []
    copied = detect_residual_english(
        field="goal",
        source="Improve client program delivery across teams",
        translated="Improve client program delivery across teams",
        target_language="fr",
    )
    assert copied


def test_terminology_protect_restore_round_trip() -> None:
    source = "Improve EBITDA with TripSource and Mission Possible for BCD"
    protected = protect_terminology(source)
    assert "EBITDA" not in protected.text
    assert "__KEEP_" in protected.text
    restored = restore_terminology(protected.text, protected.mapping)
    assert restored == source
    assert verify_preserved_terms(source=source, translated=restored) == []
    assert "EBITDA" in verify_preserved_terms(
        source=source, translated="Improve earnings with TripSource"
    )


def test_csv_and_xlsx_round_trip_key_match() -> None:
    sources = read_english_csv(_csv_bytes())
    template = read_template_workbook(_xlsx_bytes())
    result = reconcile(sources, template.records)
    assert len(result.pairs) == 2
    assert result.unmatched_source == []
    assert not result.is_blocking


def test_duplicate_and_missing_detection() -> None:
    sources = read_english_csv(_csv_bytes())
    template = read_template_workbook(_xlsx_bytes())
    template.records = template.records[:1]
    result = reconcile(sources, template.records)
    assert result.is_blocking
    assert result.unmatched_source


def test_numeric_and_quarter_validation() -> None:
    issues = compare_numeric_fields("Grow 10% by Q4 2026", "Grow 12% by Q3 2026")
    kinds = {item.kind for item in issues}
    assert "NUMERIC_DISCREPANCY" in kinds or "QUARTER_DISCREPANCY" in kinds


def test_translated_number_words_are_not_numeric_mismatches() -> None:
    """Japanese renders the word 'one' as 1つ. That digit is not a changed figure."""
    issues = compare_numeric_fields(
        "lead a practical improvement to one recurring workflow",
        "1つの定期的なワークフローに実質的な改善を主導",
    )
    assert issues == []
    changed = compare_numeric_fields("Grow 15% by Q4 2026", "Grow 12% by Q4 2026")
    assert any(item.kind == "NUMERIC_DISCREPANCY" for item in changed)
    fullwidth = compare_numeric_fields("Grow 15%", "１５％")
    assert fullwidth == []


def test_quarters_beside_chinese_characters_still_match() -> None:
    source = "1. By Q2, then by Q3 and by Q4."
    translated = "1. 通过Q2，然后通过 Q3，以及通过Q4。"
    kinds = {item.kind for item in compare_numeric_fields(source, translated)}
    assert "QUARTER_DISCREPANCY" not in kinds


def test_csv_with_language_code_column_does_not_collide() -> None:
    """Real Goals Library CSVs use Code=en on every row; that must not be the record key."""
    data = (
        b"JobLevelCode,LeaderOrNonLeader,FunctionalArea,JobFunctionCode,Category,Goal,Description,KRA,Code\n"
        b"1,Leader,Program Management,AM,Operational Productivity,Goal A,Desc A,KRA A,en\n"
        b"2,Leader,Program Management,AM,Operational Productivity,Goal A,Desc A,KRA A,en\n"
        b"1,Non-Leader,Program Management,AM,Operational Productivity,Goal B,Desc B,KRA B,en\n"
    )
    sources = read_english_csv(data)
    assert len(sources) == 3
    assert sources[0].record_key != "en"
    assert len({s.record_key for s in sources}) == 3


def test_build_workbook_from_english_csv() -> None:
    sources = read_english_csv(_csv_bytes())
    workbook_bytes = build_workbook_from_sources(sources, language_code="en")
    template = read_template_workbook(workbook_bytes)
    assert len(template.records) == 2
    assert template.records[0].goal == sources[0].goal
    assert template.records[1].kra == sources[1].kra


def test_workbook_keeps_source_columns_and_does_not_invent_goal_id() -> None:
    data = (
        b"JobLevelCode,LeaderOrNonLeader,FunctionalArea,JobFunctionCode,Category,Goal,Description,KRA,Code\n"
        b"1,Leader,Program Management,AM,Operational Productivity,Goal A,Desc A,KRA A,en\n"
    )
    sources = read_english_csv(data)
    workbook_bytes = build_workbook_from_sources(sources, language_code="hi")
    template = read_template_workbook(workbook_bytes)
    assert template.headers == [
        "JobLevelCode",
        "LeaderOrNonLeader",
        "FunctionalArea",
        "JobFunctionCode",
        "Category",
        "Goal",
        "Description",
        "KRA",
        "Code",
    ]
    assert "GoalId" not in template.headers
    assert template.records[0].goal == "Goal A"
    assert "COMPOSITE" not in " ".join(template.records[0].technical.values())


def test_excel_reconstruction_preserves_rows() -> None:
    template = read_template_workbook(_xlsx_bytes())
    output = reconstruct_workbook(
        template_bytes=_xlsx_bytes(),
        sheet_name=template.sheet_name,
        column_index=template.column_index,
        rows=[
            ExcelWriteRow(row_index=2, goal="A", description="B", kra="C"),
            ExcelWriteRow(row_index=3, goal="D", description="E", kra="F"),
        ],
        language_code="hi",
    )
    rebuilt = read_template_workbook(output)
    assert rebuilt.records[0].goal == "A"
    assert rebuilt.records[1].kra == "F"


def test_hard_gate_requires_zero_unmatched() -> None:
    failed = evaluate_hard_gate(
        {
            "source_record_count": 2,
            "output_record_count": 2,
            "unmatched_records": 1,
            "duplicate_records": 0,
            "missing_technical_fields": 0,
            "blank_goal_violations": 0,
            "blank_description_violations": 0,
            "blank_kra_violations": 0,
            "numeric_discrepancies": 0,
            "percentage_discrepancies": 0,
            "quarter_discrepancies": 0,
            "date_discrepancies": 0,
            "unresolved_high_severity_issues": 0,
            "unresolved_terminology_issues": 0,
            "hotel_revenue_growth_qa_pass": True,
            "operational_productivity_qa_pass": True,
            "workbook_post_save_integrity": True,
            "unresolved_untranslated_english": 0,
        }
    )
    assert failed.production_ready is False
    ok = evaluate_hard_gate(
        {
            "source_record_count": 2,
            "output_record_count": 2,
            "unmatched_records": 0,
            "duplicate_records": 0,
            "missing_technical_fields": 0,
            "blank_goal_violations": 0,
            "blank_description_violations": 0,
            "blank_kra_violations": 0,
            "numeric_discrepancies": 0,
            "percentage_discrepancies": 0,
            "quarter_discrepancies": 0,
            "date_discrepancies": 0,
            "unresolved_high_severity_issues": 0,
            "unresolved_terminology_issues": 0,
            "hotel_revenue_growth_qa_pass": True,
            "operational_productivity_qa_pass": True,
            "workbook_post_save_integrity": True,
            "unresolved_untranslated_english": 0,
        }
    )
    assert ok.production_ready is True


def test_structural_validator_reports_counts() -> None:
    sources = read_english_csv(_csv_bytes())
    template = read_template_workbook(_xlsx_bytes())
    reconciliation = reconcile(sources, template.records)
    result = validate_structure(sources=sources, template=template, reconciliation=reconciliation)
    assert result.source_count == 2
    assert result.ok
