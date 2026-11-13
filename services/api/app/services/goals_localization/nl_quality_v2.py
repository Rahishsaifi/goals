"""Dutch-only quality fixes (v2), gated by job option nl_quality_v2.

Other languages keep the existing translation_repair path. This module:
1. Rebuilds deadline openings from the English source (no stacked uiterlijk).
2. Restores numbered KRA measures with real newlines.
3. Detects production defects for the hard gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_BY_QX = re.compile(r"^\s*By\s+(Q[1-4])\b(.*)$", re.IGNORECASE | re.DOTALL)
_BY_END_QX = re.compile(
    r"^\s*By\s+the\s+end\s+of\s+(Q[1-4])\b(.*)$", re.IGNORECASE | re.DOTALL
)
_BY_END_YEAR = re.compile(
    r"^\s*By\s+the\s+end\s+of\s+the\s+performance\s+year\b(.*)$",
    re.IGNORECASE | re.DOTALL,
)
_AT_END_YEAR = re.compile(
    r"^\s*At\s+the\s+end\s+of\s+the\s+performance\s+year\b(.*)$",
    re.IGNORECASE | re.DOTALL,
)

_NL_DEADLINE_PREFIX = re.compile(
    r"^\s*(?:"
    r"uiterlijk\s+Q[1-4]\s+"
    r"|uiterlijk\s+in\s+Q[1-4]\s+"
    r"|uiterlijk\s+aan\s+het\s+einde\s+van\s+Q[1-4]\s+"
    r"|uiterlijk\s+aan\s+het\s+einde\s+van\s+het\s+prestatiejaar\s+"
    r"|aan\s+het\s+einde\s+van\s+het\s+prestatiejaar\s+"
    r"|uiterlijk\s+in\s+"
    r"|uiterlijk\s+"
    r")+",
    re.IGNORECASE,
)

_MEASURE = re.compile(r"(?:^|\n)\s*(\d+)\s*[\.．、]\s*", re.MULTILINE)
# Same-line join only (.2. / . 3.). A real newline before the next measure is valid.
_JOINED_NUMBER = re.compile(r"\.[^\S\n]*([2-9]|[1-9]\d+)[^\S\n]*\.")
_STACKED_DEADLINE = re.compile(
    r"uiterlijk\s+Q[1-4]\s+Uiterlijk|uiterlijk\s+in\s+uiterlijk",
    re.IGNORECASE,
)
# "uiterlijk in" that is not followed by a time expression. An earlier repair
# pulled the quarter out of "Stel uiterlijk in Q2 een basislijn vast" and left
# "stel uiterlijk in een basislijn vast" behind.
_NL_TIME_AFTER_IN = (
    r"(?:(?:het|de|dit|deze|dat|die|een)\s+)?"
    r"(?:(?:eerste|tweede|derde|vierde|laatste|komende|volgende|huidige|lopende)\s+)?"
    r"(?:Q[1-4]\b|H[12]\b|FY|\d"
    r"|januari|februari|maart|april|mei|juni|juli|augustus|september|oktober"
    r"|november|december"
    r"|kwartaal|jaar|boekjaar|prestatiejaar|maand|week|periode|halfjaar|helft"
    r"|voorjaar|najaar|zomer|winter|lente|herfst|begin|eind|midden|loop)"
)
_ORPHAN_DEADLINE = re.compile(
    rf"\buiterlijk\s+in\s+(?!{_NL_TIME_AFTER_IN})", re.IGNORECASE
)
_LOSEN = re.compile(r"\bLosen\b")
# Goals KRAs often chain deadlines with " | " instead of numbered measures.
_PIPE_SPLIT = re.compile(r"\s*\|\s*")


@dataclass(frozen=True)
class NlQualityDefects:
    stacked_deadlines: int = 0
    joined_kra_numbers: int = 0
    losen_errors: int = 0

    @property
    def total(self) -> int:
        return self.stacked_deadlines + self.joined_kra_numbers + self.losen_errors


def apply_nl_quality_v2(*, source: str, translated: str) -> str:
    """Apply Dutch v2 repairs to one field using the English source as structure."""
    if not translated:
        return translated
    text = _restore_numbered_measures(source=source, translated=translated)
    return _repair_deadlines(source=source, translated=text)


def detect_nl_quality_defects(*texts: str) -> NlQualityDefects:
    blob = "\n".join(texts)
    stacked = _STACKED_DEADLINE.findall(blob)
    # A deadline word with no date behind it is the same class of defect.
    # Counted on what is left so one stacked phrase is not reported twice.
    orphans = _ORPHAN_DEADLINE.findall(_STACKED_DEADLINE.sub(" ", blob))
    return NlQualityDefects(
        stacked_deadlines=len(stacked) + len(orphans),
        joined_kra_numbers=len(_JOINED_NUMBER.findall(blob)),
        losen_errors=len(_LOSEN.findall(blob)),
    )


def _restore_numbered_measures(*, source: str, translated: str) -> str:
    source_parts = _split_measures(source)
    translated_parts = _split_measures(translated)
    # Prefer English measure count when present; otherwise rebuild from Dutch
    # numbering alone (common when EN omits leading "1.").
    if len(source_parts) >= 2:
        by_number = {num: body for num, body in translated_parts}
        rebuilt: list[str] = []
        for index, (number, _source_body) in enumerate(source_parts):
            if number in by_number:
                body = by_number[number]
            elif index < len(translated_parts):
                body = translated_parts[index][1]
            else:
                body = ""
            body = body.strip()
            rebuilt.append(f"{number}. {body}" if body else f"{number}.")
        return "\n".join(rebuilt)
    if len(translated_parts) >= 2:
        return _join_measures(translated_parts)
    return translated


def _repair_deadlines(*, source: str, translated: str) -> str:
    source_parts = _split_measures(source)
    translated_parts = _split_measures(translated)
    if len(source_parts) >= 2:
        by_number = {num: body for num, body in translated_parts}
        rebuilt: list[str] = []
        for index, (number, source_body) in enumerate(source_parts):
            if number in by_number:
                body = by_number[number]
            elif index < len(translated_parts):
                body = translated_parts[index][1]
            else:
                body = ""
            body = _apply_deadline_for_english(source_body, body)
            rebuilt.append(f"{number}. {body}" if body else f"{number}.")
        return "\n".join(rebuilt)
    if len(translated_parts) >= 2:
        # EN had no usable numbering but Dutch does — keep NL newlines; apply
        # deadline templates only when an English body is recoverable.
        recovered_source = _split_measures(_synthesize_numbered_source(source))
        source_by_index = [body for _n, body in recovered_source]
        rebuilt: list[str] = []
        for index, (number, body) in enumerate(translated_parts):
            english = source_by_index[index] if index < len(source_by_index) else ""
            fixed = _apply_deadline_for_english(english, body)
            rebuilt.append(f"{number}. {fixed}" if fixed else f"{number}.")
        return "\n".join(rebuilt)
    piped = _repair_pipe_deadlines(source=source, translated=translated)
    if piped is not None:
        return piped
    return _apply_deadline_for_english(source, translated)


def _repair_pipe_deadlines(*, source: str, translated: str) -> str | None:
    """Repair each ' | '-separated deadline clause independently."""
    source_parts = [part.strip() for part in _PIPE_SPLIT.split(source or "") if part.strip()]
    if len(source_parts) < 2:
        return None
    translated_parts = [part.strip() for part in _PIPE_SPLIT.split(translated or "")]
    rebuilt: list[str] = []
    for index, english in enumerate(source_parts):
        dutch = translated_parts[index] if index < len(translated_parts) else ""
        rebuilt.append(_apply_deadline_for_english(english, dutch))
    for index in range(len(source_parts), len(translated_parts)):
        extra = translated_parts[index].strip()
        if extra:
            rebuilt.append(_strip_stacked_deadlines(extra).strip())
    return " | ".join(part for part in rebuilt if part)


def _join_measures(parts: list[tuple[str, str]]) -> str:
    rebuilt: list[str] = []
    for number, body in parts:
        body = body.strip()
        rebuilt.append(f"{number}. {body}" if body else f"{number}.")
    return "\n".join(rebuilt)


def _synthesize_numbered_source(source: str) -> str:
    """Prefix a leading '1.' when English starts unnumbered then hits '2.'."""
    if not source or re.match(r"^\s*\d+\s*[\.．、]", source):
        return source
    if re.search(r"(?:^|[^\d])\s*2\s*[\.．、]", source):
        return f"1. {source.strip()}"
    return source


_NL_DEADLINE_ALREADY = re.compile(
    r"(?:"
    r"uiterlijk\s+(?:in\s+)?Q[1-4]"
    r"|uiterlijk\s+aan\s+het\s+einde\s+van\s+(?:Q[1-4]|het\s+prestatiejaar)"
    r"|aan\s+het\s+einde\s+van\s+(?:Q[1-4]|het\s+prestatiejaar)"
    r")",
    re.IGNORECASE,
)


def _apply_deadline_for_english(english: str, dutch: str) -> str:
    prefix = _deadline_prefix_for(english)
    if not prefix:
        return _strip_stacked_deadlines(dutch).strip()
    body = _NL_DEADLINE_PREFIX.sub("", dutch or "").strip()
    body = _strip_stacked_deadlines(body).strip()
    # The English clause opens with its deadline, so a later "uiterlijk in"
    # with no date behind it is a leftover of an earlier repair, not content.
    body = _ORPHAN_DEADLINE.sub("", body).strip()
    if not body:
        return prefix.strip()
    if body.lower().startswith(prefix.lower().strip()):
        return body
    # Only skip stacking when THIS clause already carries the required
    # deadline (same quarter / year-end). A later " | Q3" must not block Q1.
    if _clause_already_has_required_deadline(english, body):
        return body
    if body[0].isupper() and len(body) > 1:
        body = body[0].lower() + body[1:]
    return f"{prefix}{body}"


def _deadline_prefix_for(english: str) -> str | None:
    text = english.strip()
    match = _BY_END_QX.match(text)
    if match:
        return f"Uiterlijk aan het einde van {match.group(1).upper()} "
    match = _BY_QX.match(text)
    if match:
        return f"Uiterlijk in {match.group(1).upper()} "
    match = _BY_END_YEAR.match(text)
    if match:
        return "Uiterlijk aan het einde van het prestatiejaar "
    match = _AT_END_YEAR.match(text)
    if match:
        return "Aan het einde van het prestatiejaar "
    return None


def _clause_already_has_required_deadline(english: str, dutch: str) -> bool:
    text = english.strip()
    match = _BY_END_QX.match(text) or _BY_QX.match(text)
    if match:
        quarter = match.group(1).upper()
        return bool(
            re.search(
                rf"(?:uiterlijk\s+(?:in\s+|aan\s+het\s+einde\s+van\s+)?)?{quarter}\b",
                dutch,
                flags=re.IGNORECASE,
            )
        )
    if _BY_END_YEAR.match(text) or _AT_END_YEAR.match(text):
        return bool(
            re.search(
                r"(?:uiterlijk\s+)?aan\s+het\s+einde\s+van\s+het\s+prestatiejaar",
                dutch,
                flags=re.IGNORECASE,
            )
        )
    return bool(_NL_DEADLINE_ALREADY.search(dutch))


def _strip_stacked_deadlines(text: str) -> str:
    result = text or ""
    result = re.sub(
        r"uiterlijk\s+in\s+uiterlijk\s+(?:in\s+)?(Q[1-4])\b",
        r"Uiterlijk in \1",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(
        r"uiterlijk\s+Q([1-4])\s+Uiterlijk\s+in\b",
        r"Uiterlijk in Q\1",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(
        r"uiterlijk\s+Q([1-4])\s+Uiterlijk\b",
        r"Uiterlijk in Q\1",
        result,
        flags=re.IGNORECASE,
    )
    return result


def _split_measures(text: str) -> list[tuple[str, str]]:
    if not text:
        return []
    # Joined ".2." / ". 3." patterns need a synthetic newline so numbering
    # can be recovered. Also handle "needs 3.By" (no period before the number).
    normalized = re.sub(r"\.\s*(\d+)\s*\.", r".\n\1. ", text)
    normalized = re.sub(
        r"(?<=[A-Za-zÀ-ÿ0-9])\s+([2-9]|[1-9]\d+)\s*[\.．、](?=\s*[A-Za-zÀ-ÿ])",
        r"\n\1. ",
        normalized,
    )
    matches = list(_MEASURE.finditer(normalized))
    if not matches:
        return []

    parts: list[tuple[str, str]] = []
    first = matches[0]
    # English often omits "1." and starts the body, then continues at "2.".
    if first.start() > 0 and first.group(1) == "2":
        preamble = normalized[: first.start()].strip()
        if preamble:
            parts.append(("1", preamble))
    elif first.start() > 20:
        return []

    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        parts.append((match.group(1), normalized[start:end]))
    return parts
