from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class NumericIssue:
    kind: str
    message: str
    source_values: tuple[str, ...]
    target_values: tuple[str, ...]


# Boundaries are ASCII-only. Python's \b treats Chinese characters as word
# characters, so "通过Q2" would miss Q2.
_BEFORE = r"(?<![A-Za-z0-9])"
_AFTER = r"(?![A-Za-z0-9])"
_NUMBER_RE = re.compile(
    _BEFORE + r"(?:\$|€|£)?\d{1,3}(?:[,\s]\d{3})*(?:\.\d+)?%?" + _AFTER
)
_QUARTER_RE = re.compile(
    _BEFORE + r"Q[1-4]" + _AFTER
    + "|" + _BEFORE + r"FY\s*\d{2,4}" + _AFTER
    + "|" + _BEFORE + r"20\d{2}-\d{2}" + _AFTER,
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    _BEFORE
    + r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|"
    + r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})"
    + _AFTER,
    re.IGNORECASE,
)


def _fold(text: str) -> str:
    """Map fullwidth digits and percent signs (１５％) to ASCII before matching."""
    return unicodedata.normalize("NFKC", text or "")


def _normalize_number(token: str) -> str:
    text = token.strip().replace(" ", "").replace(",", "")
    if text.endswith("%"):
        return f"{text[:-1]}%"
    return text


def extract_numbers(text: str) -> list[str]:
    return [_normalize_number(match.group(0)) for match in _NUMBER_RE.finditer(_fold(text))]


def extract_quarters(text: str) -> list[str]:
    found: list[str] = []
    for match in _QUARTER_RE.finditer(_fold(text)):
        found.append(match.group(0).upper().replace(" ", ""))
    return found


def extract_dates(text: str) -> list[str]:
    return [match.group(0) for match in _DATE_RE.finditer(_fold(text))]


def _missing_tokens(source: list[str], target: list[str]) -> bool:
    """True when a source token is absent. Extra target tokens are allowed.

    Translating the word "one" to Japanese "1つ" adds a digit that was not a
    source figure. That must not fail the check. A source "15%" that becomes
    "12%" still fails.
    """
    found = Counter(target)
    for token, count in Counter(source).items():
        if found[token] < count:
            return True
    return False


def compare_numeric_fields(source: str, target: str) -> list[NumericIssue]:
    issues: list[NumericIssue] = []
    src_nums = extract_numbers(source)
    tgt_nums = extract_numbers(target)
    if _missing_tokens(src_nums, tgt_nums):
        issues.append(
            NumericIssue(
                kind="NUMERIC_DISCREPANCY",
                message="Numeric values from the English source are missing or changed.",
                source_values=tuple(src_nums),
                target_values=tuple(tgt_nums),
            )
        )
    src_q = extract_quarters(source)
    tgt_q = extract_quarters(target)
    if _missing_tokens(src_q, tgt_q):
        issues.append(
            NumericIssue(
                kind="QUARTER_DISCREPANCY",
                message="Quarter / FY markers differ between source and translation.",
                source_values=tuple(src_q),
                target_values=tuple(tgt_q),
            )
        )
    src_d = extract_dates(source)
    tgt_d = extract_dates(target)
    if len(src_d) != len(tgt_d):
        issues.append(
            NumericIssue(
                kind="DATE_DISCREPANCY",
                message="Date / deadline markers differ between source and translation.",
                source_values=tuple(src_d),
                target_values=tuple(tgt_d),
            )
        )
    return issues
