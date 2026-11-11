from __future__ import annotations

import re
from dataclasses import dataclass

from app.goals_localization.glossary import ENGLISH_ALLOWLIST

_PHRASE_RE = re.compile(r"\b[A-Za-z]{4,}(?:\s+[A-Za-z]{4,}){2,}\b")


@dataclass(frozen=True)
class ResidualEnglishHit:
    field: str
    token: str
    message: str


def detect_residual_english(
    *,
    field: str,
    source: str,
    translated: str,
    target_language: str,
    allowlist: frozenset[str] | set[str] | None = None,
) -> list[ResidualEnglishHit]:
    """Flag suspicious English leftovers. Not proof of overall translation quality."""
    if not source.strip() or not translated.strip():
        return []
    if target_language.lower() in {"en", "en-us", "en-gb"}:
        return []
    hits: list[ResidualEnglishHit] = []
    allow = {term.lower() for term in (allowlist if allowlist is not None else ENGLISH_ALLOWLIST)}
    for match in _PHRASE_RE.finditer(source):
        phrase = match.group(0)
        words = phrase.split()
        # Allow English / Preserve may be whole phrases ("Mission Possible") or single tokens.
        if phrase.lower() in allow or all(word.lower() in allow for word in words):
            continue
        if phrase.lower() in translated.lower():
            hits.append(
                ResidualEnglishHit(
                    field=field,
                    token=phrase,
                    message=f"English phrase left unchanged: '{phrase}'.",
                )
            )
    # Deduplicate
    seen: set[str] = set()
    unique: list[ResidualEnglishHit] = []
    for hit in hits:
        key = f"{hit.field}:{hit.token}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(hit)
    return unique[:20]
