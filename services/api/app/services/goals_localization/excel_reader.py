from __future__ import annotations

import io
from dataclasses import dataclass, field

from openpyxl import load_workbook

from app.services.goals_localization.csv_reader import _HEADER_MAP, _norm_header, _stable_key


@dataclass
class TemplateRecord:
    record_key: str
    row_index: int  # 1-based Excel row
    sheet_name: str
    goal: str
    description: str
    kra: str
    technical: dict[str, str] = field(default_factory=dict)
    cells: dict[str, object] = field(default_factory=dict)


@dataclass
class TemplateWorkbookInfo:
    sheet_name: str
    headers: list[str]
    header_row: int
    column_index: dict[str, int]
    records: list[TemplateRecord]


def _cell_str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def read_template_workbook(data: bytes) -> TemplateWorkbookInfo:
    workbook = load_workbook(io.BytesIO(data))
    sheet = workbook.worksheets[0]
    header_row = 1
    headers_raw = [_cell_str(cell.value) for cell in sheet[header_row]]
    while header_row < 10 and not any(headers_raw):
        header_row += 1
        headers_raw = [_cell_str(cell.value) for cell in sheet[header_row]]
    if not any(headers_raw):
        raise ValueError("Target workbook has no header row.")

    headers: list[str] = []
    column_index: dict[str, int] = {}
    for idx, raw in enumerate(headers_raw, start=1):
        if not raw:
            continue
        canon = _HEADER_MAP.get(_norm_header(raw), raw)
        headers.append(canon)
        column_index[canon] = idx

    required = {"Goal", "Description", "KRA"}
    if not required.issubset(set(column_index)):
        missing = required - set(column_index)
        raise ValueError(f"Target workbook missing columns: {', '.join(sorted(missing))}")

    records: list[TemplateRecord] = []
    seen: set[str] = set()
    for row_idx in range(header_row + 1, sheet.max_row + 1):
        mapped: dict[str, str] = {}
        cells: dict[str, object] = {}
        empty = True
        for name, col in column_index.items():
            value = sheet.cell(row=row_idx, column=col).value
            text = _cell_str(value)
            mapped[name] = text
            cells[name] = value
            if text:
                empty = False
        if empty:
            continue
        key = _stable_key(mapped, row_idx)
        if key in seen:
            raise ValueError(f"Duplicate target record key '{key}' at row {row_idx}.")
        seen.add(key)
        technical = {
            name: mapped.get(name, "")
            for name in (
                "JobLevelCode",
                "LeaderOrNonLeader",
                "FunctionalArea",
                "JobFunctionCode",
                "Category",
                "Code",
                "GoalId",
            )
            if name in mapped
        }
        records.append(
            TemplateRecord(
                record_key=key,
                row_index=row_idx,
                sheet_name=sheet.title,
                goal=mapped.get("Goal", ""),
                description=mapped.get("Description", ""),
                kra=mapped.get("KRA", ""),
                technical=technical,
                cells=cells,
            )
        )
    if not records:
        raise ValueError("Target workbook contains no data rows.")
    return TemplateWorkbookInfo(
        sheet_name=sheet.title,
        headers=headers,
        header_row=header_row,
        column_index=column_index,
        records=records,
    )
