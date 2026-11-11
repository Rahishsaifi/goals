"""Protect approved terminology with placeholders before Azure Translator.

Flow: protect → translate → restore. Placeholders like __KEEP_001__ are unlikely
to be altered by Translator; restore puts the original terms back verbatim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.goals_localization.glossary import PRESERVE_TERMS


@dataclass(frozen=True)
class ProtectionResult:
    text: str
    mapping: dict[str, str]


def _sorted_terms() -> list[str]:
    # Longest first so "Mission Possible" wins over shorter overlaps.
    return sorted(PRESERVE_TERMS, key=len, reverse=True)


_STRUCTURAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
    re.compile(
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b",
        re.IGNORECASE,
    ),
    re.compile(r"(?<![A-Za-z])(?:\$|€|£)?\d{1,3}(?:[, ]\d{3})*(?:\.\d+)?%"),
    # Hold "By Q2" as one token. Protecting only "Q2" lets Translator turn "By"
    # into 通过 or drop it.
    re.compile(r"\b[Bb]y\s+Q[1-4]\b"),
    re.compile(r"\bQ[1-4]\b", re.IGNORECASE),
    re.compile(r"\bFY\s*\d{2,4}\b", re.IGNORECASE),
    re.compile(r"\b(?:19|20)\d{2}\b"),
)


def protect_structural(text: str) -> ProtectionResult:
    """Hold quarters, years, percentages, and dates so Translator cannot rewrite them."""
    if not text:
        return ProtectionResult(text="", mapping={})
    mapping: dict[str, str] = {}
    result = text
    for pattern in _STRUCTURAL_PATTERNS:

        def _repl(match: re.Match[str]) -> str:
            key = f"__STRUCT_{len(mapping) + 1:03d}__"
            mapping[key] = match.group(0)
            return key

        result = pattern.sub(_repl, result)
    return ProtectionResult(text=result, mapping=mapping)


def protect_terminology(text: str, *, terms: tuple[str, ...] | None = None) -> ProtectionResult:
    if not text:
        return ProtectionResult(text="", mapping={})
    mapping: dict[str, str] = {}
    result = text
    for term in sorted(terms or PRESERVE_TERMS, key=len, reverse=True):
        if not term:
            continue
        pattern = re.compile(re.escape(term), re.IGNORECASE)

        def _repl(match: re.Match[str], *, captured_term: str = term) -> str:
            # Keep source casing from the match when present.
            original = match.group(0) or captured_term
            key = f"__KEEP_{len(mapping) + 1:03d}__"
            mapping[key] = original
            return key

        result = pattern.sub(_repl, result)
    return ProtectionResult(text=result, mapping=mapping)


def restore_terminology(text: str, mapping: dict[str, str]) -> str:
    if not text or not mapping:
        return text
    result = text
    # Restore longer keys first in case of odd Translator spacing.
    for key in sorted(mapping.keys(), key=len, reverse=True):
        value = mapping[key]
        result = result.replace(key, value)
        # Translator sometimes inserts spaces inside tokens.
        spaced = key.replace("_", " _ ").replace("__", "_ _")
        if spaced != key:
            result = result.replace(spaced, value)
        result = result.replace(key.replace("_", " "), value)
    return result


def verify_preserved_terms(
    *, source: str, translated: str, terms: tuple[str, ...] | None = None
) -> list[str]:
    """Return preserve-terms present in source but missing from translation."""
    missing: list[str] = []
    for term in sorted(terms if terms is not None else _sorted_terms(), key=len, reverse=True):
        if re.search(re.escape(term), source, flags=re.IGNORECASE) and not re.search(
            re.escape(term), translated, flags=re.IGNORECASE
        ):
            missing.append(term)
    return missing
