"""Approved terminology glossary for Goals Library Localization."""

from __future__ import annotations

import re

GLOSSARY_VERSION = "2026-11-v4"

# Preserve these tokens exactly in the target language (business proper nouns / acronyms).
PRESERVE_TERMS: tuple[str, ...] = (
    "BCD",
    "NDC",
    "EBITDA",
    "TripSource",
    "GetGoing",
    "Advito",
    "Mission Possible",
    "Performance Solutions",
)

# Terms allowed to remain in English when residual-English detection runs.
ENGLISH_ALLOWLIST: frozenset[str] = frozenset(
    {
        *PRESERVE_TERMS,
        "SAP",
        "SuccessFactors",
        "KPI",
        "KRA",
        "Q1",
        "Q2",
        "Q3",
        "Q4",
        "FY",
        "OKR",
        "HR",
        "IT",
        "CEO",
        "CFO",
        "CTO",
        # Named EHS system only — ordinary team/service phrases must be translated.
    }
)

# Optional approved translations for common HR phrasing (source English -> target code -> phrase).
# Used as soft guidance for correction prompts; Translator still owns primary translation.
APPROVED_PHRASES: dict[str, dict[str, str]] = {
    "year-end": {
        "fr": "fin d'année",
        "de": "Jahresende",
        "es": "fin de año",
        "hi": "वर्ष के अंत",
    },
    "key result area": {
        "fr": "domaine de résultat clé",
        "de": "Schlüssel-Ergebnisbereich",
        "es": "área de resultado clave",
        "hi": "मुख्य परिणाम क्षेत्र",
    },
}


def apply_preserve_terms(source: str, translated: str, terms: tuple[str, ...] | None = None) -> str:
    """Ensure preserved glossary terms from the source remain intact in the translation."""
    result = translated
    for term in sorted(terms if terms is not None else PRESERVE_TERMS, key=len, reverse=True):
        source_match = re.search(re.escape(term), source, flags=re.IGNORECASE)
        if not source_match:
            continue
        if re.search(re.escape(term), result, flags=re.IGNORECASE):
            continue
        # Prefer the exact casing found in the source when the term was dropped.
        original = source_match.group(0)
        result = f"{result} {original}".strip() if result else original
    return result
