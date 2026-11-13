from __future__ import annotations

from app.services.goals_localization.nl_quality_v2 import (
    apply_nl_quality_v2,
    detect_nl_quality_defects,
)


def test_stacked_deadline_is_rewritten_from_english() -> None:
    source = "1. By Q2 select a recurring workflow. 2. By Q3 implement the change."
    translated = (
        "1. uiterlijk Q2 Uiterlijk in selecteer je een terugkerende workflow. "
        "2. uiterlijk Q3 Uiterlijk in implementeer je de wijziging."
    )

    fixed = apply_nl_quality_v2(source=source, translated=translated)

    assert "uiterlijk Q2 Uiterlijk" not in fixed
    assert "1. Uiterlijk in Q2" in fixed
    assert "2. Uiterlijk in Q3" in fixed
    assert "\n2. " in fixed


def test_kra_joined_numbers_get_newlines() -> None:
    source = "1. First measure.\n2. Second measure.\n3. Third measure."
    translated = "1. eerste maatregel.2. tweede maatregel.3. derde maatregel."

    fixed = apply_nl_quality_v2(source=source, translated=translated)

    assert "\n2. " in fixed
    assert "\n3. " in fixed
    assert ".2." not in fixed
    assert detect_nl_quality_defects(fixed).joined_kra_numbers == 0


def test_kra_joined_when_english_omits_leading_one() -> None:
    """Real Goals_en pattern: no '1.', then '. 2.' and ' 3.By' without newline."""
    source = (
        "Identify the key issues to be addressed and identify data owners. "
        "2. During the performance year, monitor and review EHSMS gaps and data needs "
        "3.By the end of the performance year, ensure that all information is complete."
    )
    translated = (
        "1. Identificeer de belangrijkste kwesties die moeten worden aangepakt "
        "en bepaal de eigenaren van de data. 2. Monitor en beoordeel gedurende "
        "het prestatiejaar de hiaten in het EHSMS en de databehoeften. 3. Zorg er "
        "aan het einde van het prestatiejaar voor dat alle informatie compleet is."
    )

    fixed = apply_nl_quality_v2(source=source, translated=translated)

    assert fixed.startswith("1. Identificeer")
    assert "\n2. Monitor" in fixed
    assert "\n3. " in fixed
    assert detect_nl_quality_defects(fixed).joined_kra_numbers == 0
    # Mid-sentence deadline already present — do not stack a second opening.
    assert fixed.lower().count("aan het einde van het prestatiejaar") == 1


def test_kra_joined_from_dutch_alone_when_source_unnumbered() -> None:
    source = "Do the first thing then the second thing then the third."
    translated = "1. eerste ding. 2. tweede ding. 3. derde ding."

    fixed = apply_nl_quality_v2(source=source, translated=translated)

    assert "\n2. " in fixed
    assert "\n3. " in fixed
    assert detect_nl_quality_defects(fixed).joined_kra_numbers == 0


def test_pipe_separated_deadlines_restore_missing_quarter() -> None:
    """Real hard-gate miss: By Q1 | By Q3 — Q1 dropped; later Q3 must not block it."""
    source = (
        "By Q1, identify the applicable implementations and establish a baseline. "
        "| By Q3, put repeatable configuration into use."
    )
    translated = (
        "identificeer je de toepasselijke implementaties en stel je een basislijn vast. "
        "| Uiterlijk in uiterlijk Q3 neem je herhaalbare configuratie in gebruik."
    )

    fixed = apply_nl_quality_v2(source=source, translated=translated)

    assert "Uiterlijk in Q1" in fixed
    assert "Uiterlijk in Q3" in fixed
    assert "uiterlijk in uiterlijk" not in fixed.lower()
    assert "Q1" in fixed.split("|", 1)[0]
    assert detect_nl_quality_defects(fixed).stacked_deadlines == 0


def test_year_end_deadline_templates() -> None:
    source = "By the end of the performance year deliver the plan."
    translated = "uiterlijk Q4 Uiterlijk aan het einde van het prestatiejaar lever het plan."

    fixed = apply_nl_quality_v2(source=source, translated=translated)

    assert fixed.startswith("Uiterlijk aan het einde van het prestatiejaar")
    assert "uiterlijk Q4 Uiterlijk" not in fixed


def test_defect_detector_flags_losen_and_stack() -> None:
    defects = detect_nl_quality_defects(
        "Losen gebruikersproblemen op.",
        "1. uiterlijk Q2 Uiterlijk in selecteer je iets.2. next",
    )
    assert defects.losen_errors == 1
    assert defects.stacked_deadlines == 1
    assert defects.joined_kra_numbers == 1
    assert defects.total == 3


def test_orphan_deadline_is_removed_and_counted() -> None:
    """Rows 19-36 of job 109fce9f: the quarter was moved and "uiterlijk in" stayed behind."""
    source = "1. By Q2, establish a baseline.\n2. By Q4, verify that the improvement holds."
    broken = (
        "1. Uiterlijk in Q2 stel uiterlijk in een basislijn vast.\n"
        "2. Uiterlijk in Q4 verifieer uiterlijk in dat de verbetering standhoudt."
    )
    assert detect_nl_quality_defects(broken).stacked_deadlines == 2
    fixed = apply_nl_quality_v2(source=source, translated=broken)
    assert fixed == (
        "1. Uiterlijk in Q2 stel een basislijn vast.\n"
        "2. Uiterlijk in Q4 verifieer dat de verbetering standhoudt."
    )
    assert detect_nl_quality_defects(fixed).total == 0


def test_deadline_inside_the_sentence_is_kept() -> None:
    source = "1. By Q2, establish a baseline.\n2. By Q4, verify that the improvement holds."
    good = (
        "1. Stel uiterlijk in Q2 een basislijn vast.\n"
        "2. Verifieer uiterlijk in het vierde kwartaal, in Q4, dat de verbetering standhoudt."
    )
    assert apply_nl_quality_v2(source=source, translated=good) == good
    assert detect_nl_quality_defects(good).total == 0
    assert detect_nl_quality_defects("Lever uiterlijk in maart 2027 het rapport op.").total == 0
