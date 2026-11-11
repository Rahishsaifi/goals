from __future__ import annotations

import io
from dataclasses import dataclass

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ISSUE_COLUMNS = ["Issue field", "Issue type", "Severity", "Issue details"]


@dataclass(frozen=True)
class RowIssue:
    field_name: str
    issue_type: str
    severity: str
    explanation: str


def issue_rows_filename(language_code: str) -> str:
    return f"Goals_{language_code.replace('/', '-')}_ISSUE_ROWS.xlsx"


def build_issue_rows_workbook(
    output_bytes: bytes, issues_by_row: dict[int, list[RowIssue]]
) -> bytes:
    """Copy only the rows with open hard-gate issues out of the output workbook."""
    source = load_workbook(io.BytesIO(output_bytes))
    sheet = source.worksheets[0]

    header_row = 1
    while header_row < 10 and not any(cell.value not in (None, "") for cell in sheet[header_row]):
        header_row += 1
    width = sheet.max_column
    headers = [sheet.cell(row=header_row, column=col).value for col in range(1, width + 1)]

    target = Workbook()
    out = target.active
    assert out is not None
    out.title = sheet.title[:31] or "Issue rows"
    out.append(["Source row", *headers, *ISSUE_COLUMNS])

    wrap = Alignment(wrap_text=True, vertical="top")
    for row_index in sorted(issues_by_row):
        issues = issues_by_row[row_index]
        values = [sheet.cell(row=row_index, column=col).value for col in range(1, width + 1)]
        out.append(
            [
                row_index,
                *values,
                "\n".join(issue.field_name for issue in issues),
                "\n".join(issue.issue_type for issue in issues),
                "\n".join(issue.severity for issue in issues),
                "\n".join(issue.explanation for issue in issues),
            ]
        )
        for cell in out[out.max_row][width + 1 :]:
            cell.alignment = wrap

    bold = Font(bold=True)
    issue_fill = PatternFill("solid", fgColor="FEF3C7")
    for col, cell in enumerate(out[1], start=1):
        cell.font = bold
        if col > width + 1:
            cell.fill = issue_fill
    out.freeze_panes = "B2"
    out.column_dimensions["A"].width = 11
    for col in range(1, width + 1):
        source_width = sheet.column_dimensions[get_column_letter(col)].width
        out.column_dimensions[get_column_letter(col + 1)].width = source_width or 18
    for offset, size in enumerate((16, 22, 10, 60), start=width + 2):
        out.column_dimensions[get_column_letter(offset)].width = size

    buffer = io.BytesIO()
    target.save(buffer)
    return buffer.getvalue()
