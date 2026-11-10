from __future__ import annotations

import io
from dataclasses import dataclass

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font

from app.services.goals_localization.csv_reader import GoalSourceRecord, _HEADER_MAP, _norm_header


@dataclass
class ExcelWriteRow:
    row_index: int
    goal: str
    description: str
    kra: str


def _source_headers(sources: list[GoalSourceRecord]) -> list[str]:
    shared = getattr(sources, "headers", None)
    if shared:
        return list(shared)
    if sources and sources[0].headers:
        return list(sources[0].headers)
    raise ValueError("English CSV headers are missing, so the workbook cannot keep source column order.")


def _canonical(header: str) -> str:
    return _HEADER_MAP.get(_norm_header(header), header)


def build_workbook_from_sources(
    sources: list[GoalSourceRecord], *, language_code: str = "en"
) -> bytes:
    """Copy the English CSV into a workbook with the same columns, in the same order.

    GoalId is written only when the source file has that column. The internal
    record key is never inserted as a cell.
    """
    headers = _source_headers(sources)
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Goals"
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for source in sources:
        row: list[str] = []
        for header in headers:
            canon = _canonical(header)
            if canon == "Goal":
                row.append(source.goal)
            elif canon == "Description":
                row.append(source.description)
            elif canon == "KRA":
                row.append(source.kra)
            elif canon == "Code":
                row.append(language_code)
            else:
                row.append((source.values or {}).get(header, ""))
        sheet.append(row)
    from openpyxl.utils import get_column_letter

    for index in range(1, len(headers) + 1):
        sheet.column_dimensions[get_column_letter(index)].width = 24
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def reconstruct_workbook(
    *,
    template_bytes: bytes,
    sheet_name: str,
    column_index: dict[str, int],
    rows: list[ExcelWriteRow],
    language_code: str,
    rtl: bool = False,
) -> bytes:
    workbook = load_workbook(io.BytesIO(template_bytes))
    sheet = workbook[sheet_name]

    goal_col = column_index["Goal"]
    desc_col = column_index["Description"]
    kra_col = column_index["KRA"]
    code_col = column_index.get("Code")

    for row in rows:
        sheet.cell(row=row.row_index, column=goal_col).value = row.goal
        sheet.cell(row=row.row_index, column=desc_col).value = row.description
        sheet.cell(row=row.row_index, column=kra_col).value = row.kra
        if code_col:
            sheet.cell(row=row.row_index, column=code_col).value = language_code
        if rtl:
            for col in (goal_col, desc_col, kra_col):
                cell = sheet.cell(row=row.row_index, column=col)
                cell.alignment = Alignment(
                    horizontal="right",
                    vertical=cell.alignment.vertical if cell.alignment else None,
                    wrap_text=True,
                )

    output = io.BytesIO()
    workbook.save(output)
    data = output.getvalue()

    # Post-save integrity: reopen and confirm row count + sample values.
    check = load_workbook(io.BytesIO(data))
    check_sheet = check[sheet_name]
    for row in rows[:5]:
        if str(check_sheet.cell(row=row.row_index, column=goal_col).value or "") != row.goal:
            raise ValueError("Post-save workbook integrity check failed for Goal column.")
    return data


def output_filename(language_code: str) -> str:
    safe = language_code.replace("/", "-")
    return f"Goals_{safe}.xlsx"
