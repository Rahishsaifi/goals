"""Tenant glossary used by translation and residual-English checks."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.goals_localization.glossary import ENGLISH_ALLOWLIST, GLOSSARY_VERSION, PRESERVE_TERMS
from app.models.goals_localization import LocalizationGlossary

_PROMPT_PATH = (
    Path(__file__).resolve().parents[2] / "goals_localization" / "prompts" / "semantic_revision.txt"
)
_MAX_PROMPT_CHARS = 200_000


@dataclass(frozen=True)
class GlossaryTerm:
    term: str
    action: str  # preserve | allow


@dataclass(frozen=True)
class GlossarySnapshot:
    terms: tuple[GlossaryTerm, ...]
    preserve: tuple[str, ...]
    allow: frozenset[str]
    cache_version: str


def default_terms() -> list[GlossaryTerm]:
    preserve = list(PRESERVE_TERMS)
    extras = sorted(set(ENGLISH_ALLOWLIST) - set(preserve), key=str.lower)
    return [GlossaryTerm(term=term, action="preserve") for term in preserve] + [
        GlossaryTerm(term=term, action="allow") for term in extras
    ]


def _snapshot(terms: list[GlossaryTerm]) -> GlossarySnapshot:
    preserve = tuple(term.term for term in terms if term.action == "preserve")
    allow = frozenset(term.term for term in terms)
    digest = hashlib.sha256("|".join(sorted(allow, key=str.lower)).encode()).hexdigest()[:12]
    return GlossarySnapshot(
        terms=tuple(terms),
        preserve=preserve,
        allow=allow,
        cache_version=f"{GLOSSARY_VERSION}-{digest}",
    )


def _clean_terms(raw: list[dict[str, str]]) -> list[GlossaryTerm]:
    cleaned: list[GlossaryTerm] = []
    seen: set[str] = set()
    for item in raw:
        term = str(item.get("term", "")).strip()
        action = str(item.get("action", "")).strip().lower()
        if not term or len(term) > 80:
            raise ValueError("Each term must be 1 to 80 characters.")
        if action not in {"preserve", "allow"}:
            raise ValueError("Action must be preserve or allow.")
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(GlossaryTerm(term=term, action=action))
    if not cleaned:
        raise ValueError("Keep at least one glossary term.")
    return cleaned


def paid_translator_enabled(db: Session, tenant_id: uuid.UUID) -> bool:
    row = db.get(LocalizationGlossary, tenant_id)
    return bool(row and row.paid_translator_enabled)


def set_paid_translator_enabled(db: Session, tenant_id: uuid.UUID, enabled: bool) -> bool:
    row = db.get(LocalizationGlossary, tenant_id)
    if row is None:
        row = LocalizationGlossary(
            tenant_id=tenant_id,
            terms=[{"term": term.term, "action": term.action} for term in default_terms()],
            paid_translator_enabled=enabled,
            updated_at=datetime.now(UTC),
        )
        db.add(row)
    else:
        row.paid_translator_enabled = enabled
        row.updated_at = datetime.now(UTC)
    db.flush()
    return enabled


def default_semantic_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def load_semantic_prompt(db: Session, tenant_id: uuid.UUID) -> tuple[str, bool]:
    """Return the prompt Foundry should use, and whether the tenant customized it."""
    row = db.get(LocalizationGlossary, tenant_id)
    saved = (row.semantic_prompt or "").strip() if row is not None else ""
    if not saved:
        return default_semantic_prompt(), False
    return row.semantic_prompt or default_semantic_prompt(), True


def save_semantic_prompt(db: Session, tenant_id: uuid.UUID, prompt: str) -> tuple[str, bool]:
    text = prompt.strip()
    if len(text) > _MAX_PROMPT_CHARS:
        raise ValueError(f"Prompt must be {_MAX_PROMPT_CHARS} characters or fewer.")
    default = default_semantic_prompt().strip()
    stored = None if not text or text == default else text
    row = db.get(LocalizationGlossary, tenant_id)
    if row is None:
        row = LocalizationGlossary(
            tenant_id=tenant_id,
            terms=[{"term": term.term, "action": term.action} for term in default_terms()],
            semantic_prompt=stored,
            updated_at=datetime.now(UTC),
        )
        db.add(row)
    else:
        row.semantic_prompt = stored
        row.updated_at = datetime.now(UTC)
    db.flush()
    return (stored or default_semantic_prompt(), stored is not None)


def load_glossary(db: Session, tenant_id: uuid.UUID) -> GlossarySnapshot:
    row = db.get(LocalizationGlossary, tenant_id)
    if row is None or not row.terms:
        return _snapshot(default_terms())
    return _snapshot(_clean_terms(list(row.terms)))


def save_glossary(db: Session, tenant_id: uuid.UUID, raw: list[dict[str, str]]) -> GlossarySnapshot:
    terms = _clean_terms(raw)
    row = db.get(LocalizationGlossary, tenant_id)
    payload = [{"term": term.term, "action": term.action} for term in terms]
    if row is None:
        row = LocalizationGlossary(tenant_id=tenant_id, terms=payload, updated_at=datetime.now(UTC))
        db.add(row)
    else:
        row.terms = payload
        row.updated_at = datetime.now(UTC)
    db.flush()
    return _snapshot(terms)
