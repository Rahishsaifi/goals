from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.goals_localization.glossary import GLOSSARY_VERSION, apply_preserve_terms
from app.models.goals_localization import TranslationCacheEntry
from app.services.goals_localization.terminology_protection import (
    protect_structural,
    protect_terminology,
    restore_terminology,
)

logger = logging.getLogger(__name__)


class TranslatorError(RuntimeError):
    pass


@dataclass
class TranslationItem:
    item_id: str
    text: str


@dataclass
class TranslationResult:
    item_id: str
    text: str
    cached: bool = False


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _MinuteCharacterBudget:
    """Hold sends so a free Translator account stays under its per-minute character window."""

    def __init__(self, limit: int) -> None:
        self.limit = max(1, limit)
        self.sent: list[tuple[float, int]] = []

    def acquire(self, characters: int) -> None:
        if characters <= 0:
            return
        while True:
            now = time.monotonic()
            self.sent = [(stamp, count) for stamp, count in self.sent if now - stamp < 60.0]
            used = sum(count for _, count in self.sent)
            if characters > self.limit or used + characters <= self.limit:
                self.sent.append((now, characters))
                return
            wait = 60.0 - (now - self.sent[0][0]) + 0.5
            logger.info(
                "translator_pace wait_seconds=%.1f used=%s next=%s limit=%s",
                wait,
                used,
                characters,
                self.limit,
            )
            time.sleep(wait)


class AzureTranslatorClient:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        region: str | None,
        batch_size: int = 50,
        timeout_seconds: float = 60.0,
        chars_per_minute: int = 30000,
        fallback: AzureTranslatorClient | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.region = region
        self.batch_size = max(1, batch_size)
        self.timeout_seconds = timeout_seconds
        self.chars_per_minute = max(1, chars_per_minute)
        self.budget = _MinuteCharacterBudget(self.chars_per_minute)
        self.fallback = fallback

    def _character_chunks(self, items: list[TranslationItem]) -> list[list[TranslationItem]]:
        chunks: list[list[TranslationItem]] = []
        current: list[TranslationItem] = []
        current_chars = 0
        # Keep each call under both the batch size and the one-minute character budget.
        max_chars = min(25000, self.chars_per_minute)
        for item in items:
            size = len(item.text)
            if current and (len(current) >= self.batch_size or current_chars + size > max_chars):
                chunks.append(current)
                current = []
                current_chars = 0
            current.append(item)
            current_chars += size
        if current:
            chunks.append(current)
        return chunks

    def translate_batch(
        self, *, items: list[TranslationItem], to_language: str, from_language: str = "en"
    ) -> list[TranslationResult]:
        if not items:
            return []
        outputs: list[TranslationResult] = []
        for chunk in self._character_chunks(items):
            self.budget.acquire(sum(len(item.text) for item in chunk))
            outputs.extend(self._translate_chunk(chunk, to_language=to_language, from_language=from_language))
        return outputs

    def _translate_chunk(
        self,
        chunk: list[TranslationItem],
        *,
        to_language: str,
        from_language: str,
    ) -> list[TranslationResult]:
        url = f"{self.endpoint}/translate"
        params = {"api-version": "3.0", "from": from_language, "to": to_language}
        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Content-Type": "application/json",
        }
        if self.region:
            headers["Ocp-Apim-Subscription-Region"] = self.region
        body = [{"text": item.text} for item in chunk]
        last_error: Exception | None = None
        for attempt in range(8):
            try:
                response = httpx.post(
                    url,
                    params=params,
                    headers=headers,
                    json=body,
                    timeout=self.timeout_seconds,
                )
                if response.status_code in {429, 500, 502, 503, 504}:
                    retry_after = response.headers.get("retry-after")
                    try:
                        header_delay = float(retry_after) if retry_after else 0.0
                    except ValueError:
                        header_delay = 0.0
                    # 429001 is the F0 per-minute window. A few short retries all fail inside it.
                    delay = min(60.0, max(header_delay, 10.0 * (attempt + 1)))
                    logger.warning(
                        "translator_retry status=%s attempt=%s delay=%s",
                        response.status_code,
                        attempt + 1,
                        delay,
                    )
                    time.sleep(delay)
                    last_error = TranslatorError(
                        f"Translator HTTP {response.status_code}: {response.text[:300]}"
                    )
                    continue
                if response.status_code >= 400:
                    raise TranslatorError(
                        f"Translator HTTP {response.status_code}: {response.text[:500]}"
                    )
                payload = response.json()
                if not isinstance(payload, list) or len(payload) != len(chunk):
                    raise TranslatorError("Translator returned unexpected payload shape.")
                results: list[TranslationResult] = []
                for item, entry in zip(chunk, payload, strict=True):
                    translations = entry.get("translations") if isinstance(entry, dict) else None
                    if not translations:
                        raise TranslatorError("Translator response missing translations.")
                    text = str(translations[0].get("text", ""))
                    results.append(
                        TranslationResult(
                            item_id=item.item_id,
                            text=text,
                            cached=False,
                        )
                    )
                return results
            except httpx.HTTPError as exc:
                last_error = TranslatorError(f"Translator network error: {exc}")
                time.sleep(min(30.0, 0.5 * (2**attempt)))
        if self.fallback is not None and last_error is not None and "429" in str(last_error):
            logger.warning("translator_paid_fallback to_language=%s", to_language)
            return self.fallback._translate_chunk(
                chunk, to_language=to_language, from_language=from_language
            )
        raise TranslatorError(str(last_error) if last_error else "Translator failed.")


class CachedTranslator:
    def __init__(self, client: AzureTranslatorClient, db: Session, *, tenant_id) -> None:
        self.client = client
        self.db = db
        self.tenant_id = tenant_id
        self.characters_sent = 0
        self.cache_hits = 0

    def translate_fields(
        self,
        *,
        records: list[dict[str, str]],
        to_language: str,
        preserve_terms: tuple[str, ...] | None = None,
        glossary_version: str = GLOSSARY_VERSION,
        on_progress: Callable[[int], None] | None = None,
    ) -> dict[str, dict[str, str]]:
        """records: [{id, goal, description, kra}] -> {id: {goal, description, kra}}

        Protects approved terminology with placeholders before Translator, then restores.
        """
        pending: list[TranslationItem] = []
        resolved: dict[str, dict[str, str]] = {
            row["id"]: {"goal": "", "description": "", "kra": ""} for row in records
        }
        # item_id, field, source_text, placeholder_mapping
        meta: list[tuple[str, str, str, dict[str, str]]] = []

        for row in records:
            rid = row["id"]
            for field in ("goal", "description", "kra"):
                source = row.get(field, "") or ""
                if not source.strip():
                    resolved[rid][field] = ""
                    continue
                digest = source_hash(source)
                cached = self.db.scalar(
                    select(TranslationCacheEntry).where(
                        TranslationCacheEntry.tenant_id == self.tenant_id,
                        TranslationCacheEntry.source_hash == digest,
                        TranslationCacheEntry.target_language == to_language,
                        TranslationCacheEntry.glossary_version == glossary_version,
                    )
                )
                if cached is not None:
                    resolved[rid][field] = cached.translated_text
                    self.cache_hits += 1
                    continue
                structural = protect_structural(source)
                protected = protect_terminology(structural.text, terms=preserve_terms)
                mapping = {**structural.mapping, **protected.mapping}
                item_id = f"{rid}::{field}"
                pending.append(TranslationItem(item_id=item_id, text=protected.text))
                meta.append((item_id, field, source, mapping))

        pending_ids = {item_id.split("::", 1)[0] for item_id, _, _, _ in meta}
        done_ids = {rid for rid in resolved if rid not in pending_ids}

        def report() -> None:
            if on_progress is not None:
                on_progress(len(done_ids))

        report()
        if pending:
            self.characters_sent += sum(len(item.text) for item in pending)
            meta_by_id = {item_id: (field, source, mapping) for item_id, field, source, mapping in meta}
            batch = self.client.batch_size
            for start in range(0, len(pending), batch):
                chunk = pending[start : start + batch]
                translated = self.client.translate_batch(items=chunk, to_language=to_language)
                by_id = {item.item_id: item.text for item in translated}
                for item in chunk:
                    field, source, mapping = meta_by_id[item.item_id]
                    text = restore_terminology(by_id.get(item.item_id, ""), mapping)
                    text = apply_preserve_terms(source, text, preserve_terms)
                    rid, _ = item.item_id.split("::", 1)
                    resolved[rid][field] = text
                    self.db.add(
                        TranslationCacheEntry(
                            tenant_id=self.tenant_id,
                            source_hash=source_hash(source),
                            target_language=to_language,
                            glossary_version=glossary_version,
                            source_text=source,
                            translated_text=text,
                        )
                    )
                self.db.flush()
                for item in chunk:
                    rid, _ = item.item_id.split("::", 1)
                    if rid not in {other.split("::", 1)[0] for other, _, _, _ in meta[start + len(chunk) :]}:
                        done_ids.add(rid)
                report()
        return resolved


def build_translator_client(
    *,
    endpoint: str | None,
    api_key: str | None,
    region: str | None,
    batch_size: int,
    chars_per_minute: int = 30000,
    paid_endpoint: str | None = None,
    paid_key: str | None = None,
    paid_region: str | None = None,
    paid_fallback: bool = False,
) -> AzureTranslatorClient:
    if not endpoint or not api_key:
        raise TranslatorError(
            "Azure Translator is not configured. Set AZURE_TRANSLATOR_ENDPOINT and AZURE_TRANSLATOR_KEY."
        )
    fallback = None
    if paid_fallback:
        if not paid_endpoint or not paid_key:
            raise TranslatorError(
                "Paid Translator fallback is enabled, but AZURE_TRANSLATOR_PAID_ENDPOINT and AZURE_TRANSLATOR_PAID_KEY are not set."
            )
        fallback = AzureTranslatorClient(
            endpoint=paid_endpoint,
            api_key=paid_key,
            region=paid_region,
            batch_size=batch_size,
            chars_per_minute=2_000_000,
        )
    return AzureTranslatorClient(
        endpoint=endpoint,
        api_key=api_key,
        region=region,
        batch_size=batch_size,
        chars_per_minute=chars_per_minute,
        fallback=fallback,
    )
