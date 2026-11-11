"""Repair known Translator mistakes without another translation call.

Azure Translator turns "By Q2" into "通过Q2" or drops the word, and it glues a
preserved term to the next word. Foundry was marking those sentences as a pass.
These repairs run on cached and fresh text so the workbook does not keep them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.goals_localization.glossary import PRESERVE_TERMS

_BY_QUARTER = re.compile(r"(\d+)\.\s*[Bb]y\s+(Q[1-4])\b|[Bb]y\s+(Q[1-4])\b")
_BARE_BY = re.compile(r"\b[Bb]y\s+(Q[1-4])\b")

# Azure translator code or selector code -> phrase with {q}.
_DEADLINE: dict[str, str] = {
    "zh": "在{q}之前",
    "ja": "{q}までに",
    "de": "bis {q}",
    "nl": "uiterlijk {q}",
    "fr": "d'ici {q}",
    "es": "antes de {q}",
    "pt": "até {q}",
    "it": "entro {q}",
    "pl": "do {q}",
    "cs": "do {q}",
    "en": "By {q}",
}

_ACCEPTED: dict[str, tuple[str, ...]] = {
    "zh": (r"在\s*{q}\s*之前", r"到\s*{q}", r"{q}\s*之前", r"{q}\s*前", r"{q}\s*为止"),
    "ja": (r"{q}\s*まで",),
    "de": (r"\bbis\s+{q}\b", r"spätestens\s+{q}"),
    "nl": (r"uiterlijk\s+{q}", r"vóór\s+{q}", r"voor\s+{q}"),
    "fr": (r"d['’]ici\s+{q}", r"avant\s+{q}"),
    "es": (r"antes\s+de\s+{q}", r"para\s+{q}"),
    "pt": (r"até\s+{q}", r"ate\s+{q}"),
    "it": (r"entro\s+{q}",),
    "pl": (r"\bdo\s+{q}\b",),
    "cs": (r"\bdo\s+{q}\b",),
    "en": (r"\b[Bb]y\s+{q}\b",),
}


@dataclass(frozen=True)
class TranslationDefect:
    type: str
    explanation: str


def language_key(code: str) -> str:
    key = (code or "").strip().lower()
    if key in {"zh-hans", "zh-cn", "zh"}:
        return "zh"
    if key in {"fr-ca", "fr"}:
        return "fr"
    if key in {"es-latam", "es"}:
        return "es"
    if key in {"pt-br", "pt"}:
        return "pt"
    if key in {"en-gb", "en"}:
        return "en"
    return key


def deadline_phrase(language: str, quarter: str) -> str:
    template = _DEADLINE.get(language_key(language), "By {q}")
    return template.format(q=quarter.upper())


def repair_translation(
    source: str,
    translated: str,
    language: str,
    terms: tuple[str, ...] | None = None,
) -> str:
    if not translated:
        return translated
    text = _separate_terms(source, translated, terms if terms is not None else PRESERVE_TERMS)
    return _repair_deadlines(source, text, language_key(language))


def find_meaning_defects(source: str, translated: str, language: str) -> list[TranslationDefect]:
    """Issues that must not be marked as a pass, even if the model says PASS."""
    lang = language_key(language)
    defects: list[TranslationDefect] = []
    if lang == "zh" and "通过" in translated and re.search(r"通过\s*Q[1-4]", translated):
        defects.append(
            TranslationDefect(
                type="DEADLINE_MISREAD",
                explanation=' "By Qn" was translated as 通过 (pass/through). Use 在Qn之前.',
            )
        )
    for number, quarter in _numbered_deadlines(source):
        phrase = deadline_phrase(lang, quarter)
        step = re.search(rf"{number}\s*[\.．、]\s*(.{{0,80}})", translated, flags=re.DOTALL)
        opening = "" if step is None else step.group(1).lstrip()
        if not _opening_has_deadline(opening, quarter, lang):
            defects.append(
                TranslationDefect(
                    type="DEADLINE_MISREAD",
                    explanation=(
                        f'Step {number} starts with "By {quarter}" in English. '
                        f"The translation must start that step with {phrase}."
                    ),
                )
            )
    return defects


def _numbered_deadlines(source: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for match in re.finditer(r"(\d+)\.\s*[Bb]y\s+(Q[1-4])\b", source):
        found.append((match.group(1), match.group(2).upper()))
    return found


def _quarters_required(source: str) -> list[str]:
    required: list[str] = []
    for match in _BY_QUARTER.finditer(source):
        quarter = match.group(2) or match.group(3)
        if quarter:
            required.append(quarter.upper())
    return required


def _repair_deadlines(source: str, translated: str, lang: str) -> str:
    required = _quarters_required(source)
    if not required:
        return translated
    needed = set(required)
    text = translated

    def _phrase_for(match: re.Match[str]) -> str:
        quarter = match.group(1).upper()
        if quarter not in needed:
            return match.group(0)
        return deadline_phrase(lang, quarter)

    if lang == "zh":
        text = re.sub(r"通过\s*(Q[1-4])", _phrase_for, text, flags=re.IGNORECASE)
    if lang != "en":
        text = re.sub(r"\b[Bb]y\s+(Q[1-4])\b", _phrase_for, text)
    for quarter in dict.fromkeys(required):
        phrase = deadline_phrase(lang, quarter)
        have = _accepted_count(text, quarter, lang)
        missing = required.count(quarter) - have
        if missing <= 0:
            continue
        bare = re.compile(rf"(?<![A-Za-z0-9]){quarter}(?![A-Za-z0-9])", re.IGNORECASE)
        protected = _accepted_spans(text, quarter, lang)
        while missing > 0:
            replaced = False
            for match in bare.finditer(text):
                if _overlaps(match.span(), protected):
                    continue
                text = text[: match.start()] + phrase + text[match.end() :]
                missing -= 1
                replaced = True
                protected = _accepted_spans(text, quarter, lang)
                break
            if not replaced:
                break
    return _lead_numbered_steps(source, text, lang)


def _lead_numbered_steps(source: str, translated: str, lang: str) -> str:
    text = translated
    for number, quarter in _numbered_deadlines(source):
        phrase = deadline_phrase(lang, quarter)
        step = re.search(
            rf"({re.escape(number)}\s*[\.．、]\s*)(.*?)(?=\d+\s*[\.．、]|$)",
            text,
            flags=re.DOTALL,
        )
        if step is None:
            continue
        body = step.group(2)
        if body.lower().lstrip().startswith(phrase.lower()):
            continue
        if phrase.lower() not in body.lower():
            continue
        remainder = re.sub(re.escape(phrase), "", body, count=1, flags=re.IGNORECASE)
        remainder = re.sub(r"\s+", " ", remainder).strip(" ，,;；")
        spacer = "" if not remainder else " "
        replacement = f"{step.group(1)}{phrase}{spacer}{remainder}"
        text = text[: step.start()] + replacement + text[step.end() :]
    return text


def _opening_has_deadline(opening: str, quarter: str, lang: str) -> bool:
    for pattern in _ACCEPTED.get(lang, (rf"\b[Bb]y\s+{quarter}\b",)):
        if re.match(pattern.format(q=quarter), opening, flags=re.IGNORECASE):
            return True
    return False


def _accepted_count(text: str, quarter: str, lang: str) -> int:
    return len(_accepted_spans(text, quarter, lang))


def _accepted_spans(text: str, quarter: str, lang: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    patterns = _ACCEPTED.get(lang, (rf"\b[Bb]y\s+{quarter}\b",))
    for pattern in patterns:
        for match in re.finditer(pattern.format(q=quarter), text, flags=re.IGNORECASE):
            spans.append(match.span())
    return spans


def _overlaps(span: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(not (end <= left or start >= right) for left, right in spans)


def _separate_terms(source: str, translated: str, terms: tuple[str, ...]) -> str:
    result = translated
    for term in sorted(terms, key=len, reverse=True):
        if not term or not re.search(re.escape(term), source, flags=re.IGNORECASE):
            continue
        escaped = re.escape(term)
        result = re.sub(rf"(?<=[A-Za-z])({escaped})", r" \1", result)
        result = re.sub(rf"({escaped})(?=[A-Za-z])", r"\1 ", result)
    return result

