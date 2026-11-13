"""Paginated JSON preview of a Goals localization output workbook."""

from __future__ import annotations

import io
from collections.abc import Collection
from typing import Any

from openpyxl import load_workbook


def preview_workbook(
    data: bytes,
    *,
    offset: int = 0,
    limit: int = 50,
    q: str = "",
    only_excel_rows: Collection[int] | None = None,
) -> dict[str, Any]:
    """Return headers + a page of data rows from the first sheet.

    ``excel_row`` is 1-based (row 1 = header). Data rows start at 2.
    When ``only_excel_rows`` is set, only those Excel rows are returned
    (still paginated / searchable).
    """
    offset = max(0, offset)
    limit = max(1, min(limit, 200))
    needle = q.strip().casefold()
    allow = {int(row) for row in only_excel_rows} if only_excel_rows is not None else None

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        sheet = workbook.worksheets[0]
        sheet_name = sheet.title
        rows_iter = sheet.iter_rows(values_only=True)
        header_raw = next(rows_iter, None)
        if header_raw is None:
            return {
                "sheet_name": sheet_name,
                "headers": [],
                "rows": [],
                "total_rows": 0,
                "offset": offset,
                "limit": limit,
                "q": q,
            }
        headers = ["" if cell is None else str(cell) for cell in header_raw]
        matched: list[dict[str, Any]] = []
        total = 0
        excel_row = 1
        for values in rows_iter:
            excel_row += 1
            if allow is not None and excel_row not in allow:
                continue
            cells = ["" if cell is None else _cell_str(cell) for cell in values]
            if len(cells) < len(headers):
                cells.extend([""] * (len(headers) - len(cells)))
            elif len(cells) > len(headers):
                cells = cells[: len(headers)]
            if needle and needle not in " ".join(cells).casefold():
                continue
            total += 1
            if total <= offset:
                continue
            if len(matched) >= limit:
                continue
            matched.append({"excel_row": excel_row, "cells": cells})
        return {
            "sheet_name": sheet_name,
            "headers": headers,
            "rows": matched,
            "total_rows": total,
            "offset": offset,
            "limit": limit,
            "q": q,
        }
    finally:
        workbook.close()


def _cell_str(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
