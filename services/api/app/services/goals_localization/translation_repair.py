"""Repair known Translator mistakes without another translation call.

Azure Translator turns "By Q2" into "通过Q2" or drops the word, and it glues a
preserved term to the next word. These repairs run on cached and fresh text.

Rule for deadlines: this module may only ADD a quarter that is missing. It
never moves, rewrites, or duplicates a deadline that is already expressed.
Text that is already correct must come back byte-for-byte unchanged, because
this runs on Foundry's revised sentences as well as on raw Translator output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.goals_localization.glossary import PRESERVE_TERMS

_BY_QUARTER = re.compile(r"(\d+)\.\s*[Bb]y\s+(Q[1-4])\b|[Bb]y\s+(Q[1-4])\b")
_BY_QX_OPEN = re.compile(r"^\s*By\s+(Q[1-4])\b", re.IGNORECASE)
# Capturing split keeps the original separators so text can be rejoined as written.
_PIPE = re.compile(r"(\s*\|\s*)")
_CJK = frozenset({"zh", "ja"})
_LEAD_CHARS = " \t\r\n,，、:：;；-–—"

# Azure translator code or selector code -> phrase with {q}.
_DEADLINE: dict[str, str] = {
    "zh": "在{q}之前",
    "ja": "{q}までに",
    "de": "bis {q}",
    "nl": "uiterlijk in {q}",
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
    "nl": (
        r"uiterlijk\s+in\s+{q}",
        r"uiterlijk\s+{q}",
        r"vóór\s+{q}",
        r"voor\s+{q}",
    ),
    "fr": (r"d['’]ici\s+{q}", r"avant\s+{q}"),
    "es": (r"antes\s+de\s+{q}", r"para\s+{q}"),
    "pt": (r"até\s+{q}", r"ate\s+{q}"),
    "it": (r"entro\s+{q}",),
    "pl": (r"\bdo\s+{q}\b",),
    "cs": (r"\bdo\s+{q}\b",),
    "en": (r"\b[Bb]y\s+{q}\b",),
}

# A quarter that directly follows one of these already sits inside a time
# expression ("in Q2", "im Q2", "au Q2"). Wrapping it would produce
# "in uiterlijk in Q2", so it is left for the semantic review instead.
_TIME_WORDS: frozenset[str] = frozenset(
    {
        # nl
        "uiterlijk", "in", "vóór", "voor", "tegen", "tot", "eind", "einde", "na",
        "tijdens", "vanaf", "per", "binnen", "van", "kwartaal",
        # de
        "bis", "spätestens", "vor", "im", "zum", "ab", "nach", "während", "ende",
        "von", "des", "quartal",
        # fr
        "ici", "avant", "en", "au", "fin", "à", "après", "pendant", "dès", "du",
        "de", "le", "la", "trimestre",
        # es / pt / it
        "para", "hasta", "durante", "del", "el", "al", "finales", "até", "ate",
        "em", "no", "do", "o", "entro", "nel", "il", "trimestre",
        # pl / cs
        "w", "przed", "na", "po", "końca", "koniec", "v", "ve", "před", "konce",
        "kwartał", "kwartale", "čtvrtletí",
    }
)


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
    *,
    restore_measures: bool = False,
) -> str:
    """Fix glued terms and missing quarters. Correct text is returned unchanged.

    ``restore_measures`` (quality v2) also puts each numbered KRA measure on
    its own line, and only when every source measure number is found.
    """
    if not translated:
        return translated
    lang = language_key(language)
    text = _separate_terms(source, translated, terms if terms is not None else PRESERVE_TERMS)
    if restore_measures:
        text = _restore_numbered_measures(source=source, translated=text)
    return _repair_deadlines(source, text, lang)


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
    marks = _step_marks(translated, _step_count(source))
    for number, quarter in _numbered_deadlines(source):
        phrase = deadline_phrase(lang, quarter)
        body = _step_body(translated, marks, int(number) - 1)
        if body is None or not _has_deadline(body, quarter, lang):
            defects.append(
                TranslationDefect(
                    type="DEADLINE_MISREAD",
                    explanation=(
                        f'Step {number} starts with "By {quarter}" in English. '
                        f"The translation must keep that deadline, e.g. {phrase}."
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


def _step_marker(number: int) -> re.Pattern[str]:
    # "2." that starts a measure: not part of a word, a quarter ("Q2."), a
    # decimal ("2.5") or a dotted number ("1.2.").
    return re.compile(rf"(?<![A-Za-z0-9,])(?<!\d\.){number}\s*[\.．、](?!\d)")


def _step_count(text: str) -> int:
    """How many measures are numbered 1., 2., 3. … in order."""
    position = 0
    number = 1
    while True:
        match = _step_marker(number).search(text or "", position)
        if match is None:
            return number - 1
        position = match.end()
        number += 1


def _step_marks(text: str, count: int) -> list[tuple[int, int]] | None:
    """Span of each "N." marker for N = 1..count, or None if any is missing."""
    marks: list[tuple[int, int]] = []
    position = 0
    for number in range(1, count + 1):
        match = _step_marker(number).search(text or "", position)
        if match is None:
            return None
        marks.append(match.span())
        position = match.end()
    return marks


def _step_body(text: str, marks: list[tuple[int, int]] | None, index: int) -> str | None:
    if marks is None or index < 0 or index >= len(marks):
        return None
    end = marks[index + 1][0] if index + 1 < len(marks) else len(text)
    return text[marks[index][1] : end]


def _repair_deadlines(source: str, translated: str, lang: str) -> str:
    required = _quarters_required(source)
    if not required or lang == "en":
        return translated
    needed = set(required)

    def _phrase_for(match: re.Match[str]) -> str:
        quarter = match.group(1).upper()
        if quarter not in needed:
            return match.group(0)
        return deadline_phrase(lang, quarter)

    # Explicit misreads: 通过Qn ("through Qn") and an English "By Qn" left as is.
    text = translated
    if lang == "zh":
        text = re.sub(r"通过\s*(Q[1-4])", _phrase_for, text, flags=re.IGNORECASE)
    text = re.sub(r"\b[Bb]y\s+(Q[1-4])\b", _phrase_for, text)

    source_parts = _PIPE.split(source)[::2]
    if len([part for part in source_parts if part.strip()]) >= 2:
        pieces = _PIPE.split(text)
        if len(pieces[::2]) != len(source_parts):
            # Clause structure differs from the source: do not guess.
            return text
        for index, english in enumerate(source_parts):
            pieces[2 * index] = _repair_clause(english, pieces[2 * index], lang)
        return "".join(pieces)
    return _repair_clause(source, text, lang)


def _repair_clause(english: str, target: str, lang: str) -> str:
    steps = _numbered_deadlines(english)
    if steps:
        marks = _step_marks(target, _step_count(english))
        if marks is None:
            return target
        # Last step first so earlier offsets stay valid.
        for number, quarter in reversed(steps):
            index = int(number) - 1
            body = _step_body(target, marks, index)
            if body is None:
                continue
            start = marks[index][1]
            fixed = _ensure_quarter(body, quarter, lang)
            target = target[:start] + fixed + target[start + len(body) :]
        return target
    opening = _BY_QX_OPEN.match(english or "")
    if opening:
        return _ensure_quarter(target, opening.group(1).upper(), lang)
    return target


def _has_deadline(body: str, quarter: str, lang: str) -> bool:
    if _accepted_spans(body, quarter, lang):
        return True
    bare = _bare_quarter(body, quarter)
    return bare is not None and _previous_word(body[: bare.start()]) in _TIME_WORDS


def _bare_quarter(body: str, quarter: str) -> re.Match[str] | None:
    return re.search(rf"(?<![A-Za-z0-9]){quarter}(?![A-Za-z0-9])", body, flags=re.IGNORECASE)


def _previous_word(before: str) -> str:
    match = re.search(r"([^\W\d_]+)\W*$", before)
    return match.group(1).lower() if match else ""


def _ensure_quarter(body: str, quarter: str, lang: str) -> str:
    """Make sure one step/clause carries its quarter. Never relocates text."""
    if _accepted_spans(body, quarter, lang):
        return body
    phrase = deadline_phrase(lang, quarter)
    bare = _bare_quarter(body, quarter)
    if bare is not None:
        before = body[: bare.start()]
        at_start = not before.strip(_LEAD_CHARS)
        if at_start:
            head = phrase if lang in _CJK else phrase[0].upper() + phrase[1:]
            return before + head + body[bare.end() :]
        if lang not in _CJK and _previous_word(before) not in _TIME_WORDS:
            return before + phrase + body[bare.end() :]
        # Already inside a time expression such as "in Q2": leave it alone.
        return body
    # The quarter was dropped entirely: put the deadline in front.
    stripped = body.lstrip()
    if not stripped:
        return body
    lead = body[: len(body) - len(stripped)]
    if lang in _CJK:
        return f"{lead}{phrase}{stripped}"
    head = phrase[0].upper() + phrase[1:]
    # German capitalises nouns, so its first word is left as written.
    if lang != "de" and len(stripped) > 1 and stripped[0].isupper() and stripped[1].islower():
        stripped = stripped[0].lower() + stripped[1:]
    return f"{lead}{head} {stripped}"


def _restore_numbered_measures(*, source: str, translated: str) -> str:
    """Start each numbered measure on its own line.

    Only when every measure number from the source is found in the
    translation. Otherwise the text is returned untouched.
    """
    count = _step_count(source)
    if count < 2:
        return translated
    marks = _step_marks(translated, count)
    if marks is None:
        return translated
    text = translated
    for start, _end in reversed(marks[1:]):
        head = text[:start].rstrip(" \t")
        if head.endswith("\n"):
            continue
        text = head + "\n" + text[start:]
    return text


def _accepted_spans(text: str, quarter: str, lang: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    patterns = _ACCEPTED.get(lang, (rf"\b[Bb]y\s+{quarter}\b",))
    for pattern in patterns:
        for match in re.finditer(pattern.format(q=quarter), text, flags=re.IGNORECASE):
            spans.append(match.span())
    return spans


def _separate_terms(source: str, translated: str, terms: tuple[str, ...]) -> str:
    result = translated
    for term in sorted(terms, key=len, reverse=True):
        if not term or not re.search(re.escape(term), source, flags=re.IGNORECASE):
            continue
        escaped = re.escape(term)
        result = re.sub(rf"(?<=[A-Za-z])({escaped})", r" \1", result)
        result = re.sub(rf"({escaped})(?=[A-Za-z])", r"\1 ", result)
    return result
