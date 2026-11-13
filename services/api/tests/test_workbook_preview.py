import io

from openpyxl import Workbook

from app.services.goals_localization.workbook_preview import preview_workbook


def _sample_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Goal", "KRA"])
    ws.append(["A", "By Q1 ship"])
    ws.append(["B", "ok"])
    ws.append(["C", "By Q2 ship"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_preview_paginates_and_filters_issue_rows() -> None:
    data = _sample_bytes()
    page = preview_workbook(data, offset=0, limit=2)
    assert page["total_rows"] == 3
    assert [row["excel_row"] for row in page["rows"]] == [2, 3]

    issues = preview_workbook(data, only_excel_rows={2, 4}, offset=0, limit=50)
    assert issues["total_rows"] == 2
    assert [row["excel_row"] for row in issues["rows"]] == [2, 4]
    assert "Q1" in issues["rows"][0]["cells"][1]
