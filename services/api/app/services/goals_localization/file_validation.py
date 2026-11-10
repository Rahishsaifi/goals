from __future__ import annotations

import csv
import io
from dataclasses import dataclass


class FileValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedUpload:
    kind: str
    filename: str
    content_type: str
    size_bytes: int
    data: bytes


def _ext(filename: str) -> str:
    name = filename.rsplit("/", 1)[-1]
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1].lower()


def validate_english_csv(*, filename: str, data: bytes, max_bytes: int) -> ValidatedUpload:
    if not filename:
        raise FileValidationError("English Goals Library filename is required.")
    if _ext(filename) != "csv":
        raise FileValidationError("English Goals Library must be a .csv file.")
    if not data:
        raise FileValidationError("English Goals Library file is empty.")
    if len(data) > max_bytes:
        raise FileValidationError(f"English CSV exceeds max size of {max_bytes} bytes.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FileValidationError("English CSV must be UTF-8 encoded.") from exc
    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        headers = [h.strip() for h in (reader.fieldnames or [])]
    except csv.Error as exc:
        raise FileValidationError(f"English CSV is not readable: {exc}") from exc
    required = {"Goal", "Description", "KRA"}
    missing = required - set(headers)
    if missing:
        # Allow case-insensitive header match later in reader; only fail if none present.
        lowered = {h.lower() for h in headers}
        if not {"goal", "description", "kra"}.issubset(lowered):
            raise FileValidationError(
                f"English CSV missing required columns: {', '.join(sorted(missing))}"
            )
    return ValidatedUpload(
        kind="english_csv",
        filename=filename,
        content_type="text/csv",
        size_bytes=len(data),
        data=data,
    )


def validate_template_xlsx(*, filename: str, data: bytes, max_bytes: int) -> ValidatedUpload:
    if not filename:
        raise FileValidationError("Target workbook filename is required.")
    if _ext(filename) not in {"xlsx"}:
        raise FileValidationError("Target workbook must be a .xlsx file.")
    if not data:
        raise FileValidationError("Target workbook file is empty.")
    if len(data) > max_bytes:
        raise FileValidationError(f"Target workbook exceeds max size of {max_bytes} bytes.")
    # ZIP/XLSX magic
    if data[:2] != b"PK":
        raise FileValidationError("Target workbook is not a valid XLSX (ZIP) file.")
    return ValidatedUpload(
        kind="template_xlsx",
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=len(data),
        data=data,
    )
