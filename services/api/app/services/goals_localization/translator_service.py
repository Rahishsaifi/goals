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
from app.services.goals_localization.translation_repair import repair_translation

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
        self.on_wait: Callable[[float], None] | None = None

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
            if self.on_wait is not None:
                self.on_wait(wait)
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
        # 0 means no app-side character pace. Used for the paid Translator account.
        self.chars_per_minute = max(0, chars_per_minute)
        self.budget = _MinuteCharacterBudget(self.chars_per_minute) if self.chars_per_minute else None
        self.fallback = fallback
        # (level, message) sink for the job activity log.
        self.notify: Callable[[str, str], None] | None = None

    def set_notify(self, notify: Callable[[str, str], None] | None) -> None:
        self.notify = notify
        if self.budget is not None:
            self.budget.on_wait = (
                None
                if notify is None
                else lambda wait: notify(
                    "info",
                    f"Free Translator pacing: waiting {wait:.0f}s "
                    "to stay under the per-minute character limit.",
                )
            )

    def _emit(self, level: str, message: str) -> None:
        if self.notify is not None:
            self.notify(level, message)

    def _character_chunks(self, items: list[TranslationItem]) -> list[list[TranslationItem]]:
        chunks: list[list[TranslationItem]] = []
        current: list[TranslationItem] = []
        current_chars = 0
        # Keep each call under the Translator request cap. Free tier also stays inside one minute.
        max_chars = 45000 if self.chars_per_minute == 0 else min(25000, self.chars_per_minute)
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
            if self.budget is not None:
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
                    self._emit(
                        "warning",
                        f"Translator HTTP {response.status_code}; "
                        f"retry {attempt + 1}/8 in {delay:.0f}s.",
                    )
                    time.sleep(delay)
                    last_error = TranslatorError(
                        f"Translator HTTP {response.status_code}: {response.text[:300]}"
                    )
                    continue
                if response.status_code >= 400:
                    error = TranslatorError(
                        f"Translator HTTP {response.status_code}: {response.text[:500]}"
                    )
                    if self.fallback is not None and response.status_code in {401, 403, 429}:
                        logger.warning(
                            "translator_paid_fallback status=%s to_language=%s",
                            response.status_code,
                            to_language,
                        )
                        self._emit(
                            "warning",
                            f"Free Translator returned HTTP {response.status_code}; "
                            "sent this batch to the paid Translator.",
                        )
                        return self.fallback._translate_chunk(
                            chunk, to_language=to_language, from_language=from_language
                        )
                    raise error
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
                self._emit("warning", f"Translator network error; retry {attempt + 1}/8.")
                time.sleep(min(30.0, 0.5 * (2**attempt)))
        if self.fallback is not None and last_error is not None and "429" in str(last_error):
            logger.warning("translator_paid_fallback to_language=%s", to_language)
            self._emit(
                "warning",
                "Free Translator kept rate limiting; sent this batch to the paid Translator.",
            )
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

        Protects Preserve terms only. Allow English terms are translated normally and are
        only excluded later by residual-English QA.
        """
        resolved: dict[str, dict[str, str]] = {
            row["id"]: {"goal": "", "description": "", "kra": ""} for row in records
        }
        # One Translator call per distinct source text. Every row that repeats it reuses the result.
        groups: dict[str, dict[str, object]] = {}
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
                    fixed = repair_translation(
                        source, cached.translated_text, to_language, preserve_terms
                    )
                    if fixed != cached.translated_text:
                        cached.translated_text = fixed
                    resolved[rid][field] = fixed
                    self.cache_hits += 1
                    continue
                group = groups.get(digest)
                if group is None:
                    structural = protect_structural(source)
                    protected = protect_terminology(structural.text, terms=preserve_terms)
                    group = {
                        "source": source,
                        "protected": protected.text,
                        "mapping": {**structural.mapping, **protected.mapping},
                        "targets": [],
                    }
                    groups[digest] = group
                targets = group["targets"]
                assert isinstance(targets, list)
                targets.append((rid, field))

        remaining: dict[str, int] = {}
        for group in groups.values():
            targets = group["targets"]
            assert isinstance(targets, list)
            for rid, _field in targets:
                remaining[rid] = remaining.get(rid, 0) + 1

        def report() -> None:
            if on_progress is not None:
                on_progress(len(resolved) - len(remaining))

        report()
        if groups:
            pending = [
                TranslationItem(item_id=digest, text=str(group["protected"]))
                for digest, group in groups.items()
            ]
            self.characters_sent += sum(len(item.text) for item in pending)
            batch = max(1, self.client.batch_size)
            for start in range(0, len(pending), batch):
                chunk = pending[start : start + batch]
                translated = {
                    item.item_id: item.text
                    for item in self.client.translate_batch(items=chunk, to_language=to_language)
                }
                for item in chunk:
                    group = groups[item.item_id]
                    source = str(group["source"])
                    mapping = group["mapping"]
                    assert isinstance(mapping, dict)
                    text = restore_terminology(translated.get(item.item_id, ""), mapping)
                    text = apply_preserve_terms(source, text, preserve_terms)
                    text = repair_translation(source, text, to_language, preserve_terms)
                    targets = group["targets"]
                    assert isinstance(targets, list)
                    for rid, field in targets:
                        resolved[rid][field] = text
                        remaining[rid] -= 1
                        if remaining[rid] <= 0:
                            remaining.pop(rid, None)
                    self.db.add(
                        TranslationCacheEntry(
                            tenant_id=self.tenant_id,
                            source_hash=item.item_id,
                            target_language=to_language,
                            glossary_version=glossary_version,
                            source_text=source,
                            translated_text=text,
                        )
                    )
                self.db.flush()
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
    paid_only: bool = False,
) -> AzureTranslatorClient:
    if paid_only:
        if not paid_endpoint or not paid_key:
            raise TranslatorError(
                "AZURE_TRANSLATOR_PAID_ONLY is on, but AZURE_TRANSLATOR_PAID_ENDPOINT and AZURE_TRANSLATOR_PAID_KEY are not set."
            )
        return AzureTranslatorClient(
            endpoint=paid_endpoint,
            api_key=paid_key,
            region=paid_region,
            batch_size=batch_size,
            chars_per_minute=0,
        )
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
            chars_per_minute=0,
        )
    return AzureTranslatorClient(
        endpoint=endpoint,
        api_key=api_key,
        region=region,
        batch_size=batch_size,
        chars_per_minute=chars_per_minute,
        fallback=fallback,
    )
