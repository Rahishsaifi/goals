from __future__ import annotations

import re
from dataclasses import dataclass

from app.goals_localization.glossary import ENGLISH_ALLOWLIST

# A word, allowing internal hyphens/apostrophes ("post-launch", "in-scope").
_WORD = r"[A-Za-z]+(?:[-'’][A-Za-z]+)*"
# Words separated only by spaces. Punctuation, digits and line breaks end a run.
_RUN_RE = re.compile(rf"{_WORD}(?:[ \t]+{_WORD})+")
_MIN_LETTERS = 4
_MIN_WORDS = 2


@dataclass(frozen=True)
class ResidualEnglishHit:
    field: str
    token: str
    message: str


def _is_allowed(phrase: str, allow: set[str]) -> bool:
    low = phrase.lower()
    if low in allow:
        return True
    words = phrase.split()
    if words and all(word.lower() in allow for word in words):
        return True
    # Substring of a longer allowlisted term (e.g. "Safety Management System"
    # inside "Environmental Health and Safety Management System").
    for term in allow:
        if len(term) > len(low) and low in term:
            return True
    return False


def _letters(word: str) -> int:
    return sum(1 for char in word if char.isalpha())


def _bare(word: str) -> str:
    """Lower-case word without a possessive ending ("BCD's" -> "bcd")."""
    return re.sub(r"['’]s$", "", word.lower())


def _allowed_word_flags(words: list[str], allow: set[str]) -> list[bool]:
    """Mark words that belong to a glossary term (single word or multi-word)."""
    lowered = [_bare(word) for word in words]
    flags = [word in allow for word in lowered]
    for term in allow:
        parts = term.split()
        if len(parts) < 2:
            continue
        for start in range(len(lowered) - len(parts) + 1):
            if lowered[start : start + len(parts)] == parts:
                for offset in range(len(parts)):
                    flags[start + offset] = True
    return flags


def _candidate_phrases(source: str, allow: set[str]) -> list[str]:
    """English phrases of 2+ ordinary words, longest first, from the source.

    A phrase needs at least two words that are not glossary terms. A single
    English word next to a brand ("GetGoing platform") is not judged here:
    many single words are also valid in the target language (team, service).
    """
    candidates: list[str] = []
    for run in _RUN_RE.finditer(source):
        words = run.group(0).split()
        # Glossary terms are matched on the whole run, so a term that contains
        # a short word ("Health and Safety") is still recognised.
        run_flags = _allowed_word_flags(words, allow)
        # Short words (and, the, for) break a run into separate phrases.
        chunk: list[str] = []
        chunk_flags: list[bool] = []
        chunks: list[tuple[list[str], list[bool]]] = []
        for word, flag in zip(words, run_flags, strict=True):
            if _letters(word) >= _MIN_LETTERS:
                chunk.append(word)
                chunk_flags.append(flag)
                continue
            if len(chunk) >= _MIN_WORDS:
                chunks.append((chunk, chunk_flags))
            chunk, chunk_flags = [], []
        if len(chunk) >= _MIN_WORDS:
            chunks.append((chunk, chunk_flags))
        for chunk, flags in chunks:
            for size in range(len(chunk), _MIN_WORDS - 1, -1):
                for start in range(len(chunk) - size + 1):
                    if flags[start : start + size].count(False) < _MIN_WORDS:
                        continue
                    phrase = " ".join(chunk[start : start + size])
                    if not _is_allowed(phrase, allow):
                        candidates.append(phrase)
    # Longest first so a 3-word leftover is reported once, not as two pairs.
    return sorted(dict.fromkeys(candidates), key=lambda item: (-len(item.split()), item.lower()))


def _find_spans(phrase: str, text: str) -> list[tuple[int, int]]:
    pattern = r"\s+".join(re.escape(word) for word in phrase.split())
    return [
        match.span()
        for match in re.finditer(rf"(?<![A-Za-z]){pattern}(?![A-Za-z])", text, flags=re.IGNORECASE)
    ]


def detect_residual_english(
    *,
    field: str,
    source: str,
    translated: str,
    target_language: str,
    allowlist: frozenset[str] | set[str] | None = None,
) -> list[ResidualEnglishHit]:
    """Flag English phrases (2+ ordinary words) copied unchanged into the translation.

    This is a check for copied phrases, not proof of overall translation
    quality, and it does not judge single English words.
    """
    if not source.strip() or not translated.strip():
        return []
    if target_language.lower() in {"en", "en-us", "en-gb"}:
        return []
    allow = {term.lower() for term in (allowlist if allowlist is not None else ENGLISH_ALLOWLIST)}
    hits: list[ResidualEnglishHit] = []
    covered: list[tuple[int, int]] = []
    for phrase in _candidate_phrases(source, allow):
        spans = [
            span
            for span in _find_spans(phrase, translated)
            if not any(left <= span[0] and span[1] <= right for left, right in covered)
        ]
        if not spans:
            continue
        covered.extend(spans)
        hits.append(
            ResidualEnglishHit(
                field=field,
                token=phrase,
                message=f"English phrase left unchanged: '{phrase}'.",
            )
        )
    hits.extend(_english_written_by_the_model(field, translated, allow, covered))
    return hits[:20]


# English function words that are not words in the supported target languages.
# They catch English the model wrote itself, which is not in the source and so
# cannot be found by comparing with it (e.g. "EHSMS" expanded to
# "Environmental Health and Safety Management System").
_FUNCTION_WORD = re.compile(r"(?<![A-Za-z'’-])(?:and|the|with)(?![A-Za-z'’-])", re.IGNORECASE)
_WORD_BEFORE = re.compile(rf"({_WORD})[ \t]+$")
_WORD_AFTER = re.compile(rf"^[ \t]+({_WORD})")


def _english_written_by_the_model(
    field: str, translated: str, allow: set[str], covered: list[tuple[int, int]]
) -> list[ResidualEnglishHit]:
    # Hide glossary terms first so "and"/"the" inside a term are not judged.
    text = translated
    for term in sorted(allow, key=len, reverse=True):
        if " " not in term:
            continue
        text = re.sub(
            rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])",
            lambda match: "#" * len(match.group(0)),
            text,
            flags=re.IGNORECASE,
        )
    found: list[ResidualEnglishHit] = []
    for match in _FUNCTION_WORD.finditer(text):
        start, end = match.span()
        # Grow over neighbouring name-like (capitalised) words, at least one each side.
        taken = 0
        while True:
            before = _WORD_BEFORE.search(text[:start])
            if before is None or (taken and not before.group(1)[0].isupper()):
                break
            start = before.start(1)
            taken += 1
        taken = 0
        while True:
            after = _WORD_AFTER.search(text[end:])
            if after is None or (taken and not after.group(1)[0].isupper()):
                break
            end += after.end(1)
            taken += 1
        if any(left <= start and end <= right for left, right in covered):
            continue
        if any(start < right and left < end for left, right in covered):
            continue
        covered.append((start, end))
        phrase = text[start:end]
        found.append(
            ResidualEnglishHit(
                field=field,
                token=phrase,
                message=f"English wording in the translation: '{phrase}'.",
            )
        )
    return found
