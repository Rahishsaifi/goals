from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field


@dataclass
class GoalSourceRecord:
    record_key: str
    goal: str
    description: str
    kra: str
    technical: dict[str, str] = field(default_factory=dict)
    row_number: int = 0
    # Original CSV header text, in source order. Shared by every row in the file.
    headers: list[str] = field(default_factory=list)
    # Cell text keyed by the original header, so the workbook can be rebuilt 1:1.
    values: dict[str, str] = field(default_factory=dict)


class GoalSourceTable(list[GoalSourceRecord]):
    """CSV rows plus the header order from the source file."""

    headers: list[str]

    def __init__(self, headers: list[str], records: list[GoalSourceRecord]) -> None:
        super().__init__(records)
        self.headers = headers


def _norm_header(value: str) -> str:
    return "".join(ch for ch in value.strip().lower() if ch.isalnum())


_HEADER_MAP = {
    "goal": "Goal",
    "description": "Description",
    "kra": "KRA",
    "goalid": "GoalId",
    "id": "GoalId",
    "code": "Code",
    "joblevelcode": "JobLevelCode",
    "leaderornonleader": "LeaderOrNonLeader",
    "functionalarea": "FunctionalArea",
    "jobfunctioncode": "JobFunctionCode",
    "category": "Category",
}


def _map_row(raw: dict[str, str | None]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for key, value in raw.items():
        if key is None:
            continue
        canon = _HEADER_MAP.get(_norm_header(key))
        if canon:
            mapped[canon] = (value or "").strip()
        else:
            mapped[key.strip()] = (value or "").strip()
    return mapped


def _looks_like_language_code(value: str) -> bool:
    """SuccessFactors 'Code' is a locale (en, hi, zh-Hans), not a row id."""
    cleaned = value.strip()
    if not cleaned:
        return False
    if cleaned.lower() in {
        "en",
        "hi",
        "ar",
        "fr",
        "de",
        "es",
        "pt",
        "ja",
        "ko",
        "it",
        "nl",
        "ru",
        "tr",
        "zh",
        "zh-hans",
        "zh-hant",
    }:
        return True
    # BCP-47-ish short tags: xx or xx-Yyyy
    parts = cleaned.replace("_", "-").split("-")
    if 1 <= len(parts) <= 2 and all(p.isalpha() and 2 <= len(p) <= 8 for p in parts):
        return len(parts[0]) <= 3
    return False


def _stable_key(mapped: dict[str, str], row_number: int) -> str:
    goal_id = mapped.get("GoalId", "").strip()
    if goal_id:
        return goal_id

    # Do not use Code: in Goals Library CSVs it is the language (often "en" on every row).
    # JobFunctionCode alone is also commonly shared across many goals.
    code = mapped.get("Code", "").strip()
    if code and not _looks_like_language_code(code):
        return code

    parts = [
        mapped.get("JobLevelCode", ""),
        mapped.get("LeaderOrNonLeader", ""),
        mapped.get("FunctionalArea", ""),
        mapped.get("JobFunctionCode", ""),
        mapped.get("Category", ""),
        mapped.get("Goal", "")[:80],
    ]
    composite = "|".join(parts)
    if composite.replace("|", ""):
        return f"COMPOSITE::{composite}"
    raise ValueError(f"Row {row_number}: cannot derive a stable record key.")


def read_english_csv(data: bytes) -> GoalSourceTable:
    text = data.decode("utf-8-sig")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = [name.strip() for name in (reader.fieldnames or []) if name and name.strip()]
    records: list[GoalSourceRecord] = []
    seen: set[str] = set()
    for index, raw in enumerate(reader, start=2):
        original = {
            (key or "").strip(): (value or "").strip()
            for key, value in raw.items()
            if key and key.strip()
        }
        mapped = _map_row(original)
        key = _stable_key(mapped, index)
        if key in seen:
            raise ValueError(f"Duplicate source record key '{key}' at CSV row {index}.")
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
            GoalSourceRecord(
                record_key=key,
                goal=mapped.get("Goal", ""),
                description=mapped.get("Description", ""),
                kra=mapped.get("KRA", ""),
                technical=technical,
                row_number=index,
                headers=headers,
                values=original,
            )
        )
    if not records:
        raise ValueError("English CSV contains no data rows.")
    return GoalSourceTable(headers, records)
