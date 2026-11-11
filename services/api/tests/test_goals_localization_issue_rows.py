from __future__ import annotations

import io

from openpyxl import Workbook, load_workbook

from app.services.goals_localization.issue_rows import (
    ISSUE_COLUMNS,
    RowIssue,
    build_issue_rows_workbook,
    issue_rows_filename,
)


def _output_workbook() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Goals"
    sheet.append(["GoalId", "Goal", "Description", "KRA", "Code"])
    for index in range(1, 6):
        sheet.append([f"G{index}", f"Doel {index}", f"Beschrijving {index}", f"KRA {index}", "nl"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_only_issue_rows_are_copied_with_issue_columns() -> None:
    issues = {
        4: [RowIssue("goal", "UNTRANSLATED_ENGLISH", "MEDIUM", "English left: revenue")],
        2: [
            RowIssue("description", "TERMINOLOGY_MISSING", "HIGH", "EBITDA missing"),
            RowIssue("kra", "UNTRANSLATED_ENGLISH", "MEDIUM", "English left: KPI"),
        ],
    }

    data = build_issue_rows_workbook(_output_workbook(), issues)

    sheet = load_workbook(io.BytesIO(data)).worksheets[0]
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0] == ("Source row", "GoalId", "Goal", "Description", "KRA", "Code", *ISSUE_COLUMNS)
    assert len(rows) == 3
    assert rows[1][:3] == (2, "G1", "Doel 1")
    assert rows[1][6:] == (
        "description\nkra",
        "TERMINOLOGY_MISSING\nUNTRANSLATED_ENGLISH",
        "HIGH\nMEDIUM",
        "EBITDA missing\nEnglish left: KPI",
    )
    assert rows[2][:3] == (4, "G3", "Doel 3")
    assert rows[2][-1] == "English left: revenue"


def test_issue_rows_filename() -> None:
    assert issue_rows_filename("nl") == "Goals_nl_ISSUE_ROWS.xlsx"
