from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import get_settings
from app.goals_localization.language_config import resolve_language, resolve_qa_mode
from app.integrations.foundry_provider import FoundryProviderError
from app.integrations.storage import BlobStorage
from app.models.goals_localization import (
    LocalizationJob,
    LocalizationJobStatus,
    LocalizationQAResult,
    LocalizationRecord,
    LocalizationRecordStatus,
)
from app.services.goals_localization.category_qa_service import validate_special_categories
from app.services.goals_localization.csv_reader import read_english_csv
from app.services.goals_localization.excel_generator import (
    ExcelWriteRow,
    build_workbook_from_sources,
    output_filename,
    reconstruct_workbook,
)
from app.services.goals_localization.excel_reader import read_template_workbook
from app.services.goals_localization.glossary_store import (
    load_glossary,
    load_semantic_prompt,
    paid_translator_enabled,
)
from app.services.goals_localization.hard_gate import evaluate_hard_gate
from app.services.goals_localization.nl_quality_v2 import (
    apply_nl_quality_v2,
    detect_nl_quality_defects,
)
from app.services.goals_localization.numeric_validator import compare_numeric_fields
from app.services.goals_localization.qa_report_generator import build_qa_report
from app.services.goals_localization.semantic_qa_service import (
    FoundryRateGate,
    build_semantic_qa_service,
)
from app.services.goals_localization.terminology_protection import verify_preserved_terms
from app.services.goals_localization.translation_repair import repair_translation
from app.services.goals_localization.translator_service import (
    CachedTranslator,
    TranslatorError,
    build_translator_client,
)
from app.services.goals_localization.untranslated_english import detect_residual_english
from app.services.processing_service import renew_outbox_lease

logger = logging.getLogger(__name__)

CONTAINER = "goals-localization"

MAX_JOB_EVENTS = 400
_last_heartbeat: dict[uuid.UUID, float] = {}

STAGE_NAMES = {
    "file_validation": "File validation",
    "english_extraction": "English source extraction",
    "record_reconciliation": "Record reconciliation",
    "translation": "Translation",
    "semantic_qa": "Semantic QA",
    "automatic_correction": "Automatic correction",
    "technical_validation": "Technical validation",
    "special_category_validation": "Special category validation",
    "excel_reconstruction": "Excel reconstruction",
    "final_hard_gate": "Final hard gate",
    "english_issue_repair": "Repair untranslated English",
}


class LocalizationCancelled(Exception):
    """The job was cancelled from the UI while the worker was running it."""


def _scan_residual_english(
    records: list[LocalizationRecord],
    *,
    language_code: str,
    allowlist: frozenset[str] | set[str],
) -> dict[tuple[uuid.UUID, str], list[str]]:
    hits: dict[tuple[uuid.UUID, str], list[str]] = {}
    for rec in records:
        for field in ("goal", "description", "kra"):
            found = detect_residual_english(
                field=field,
                source=getattr(rec, f"source_{field}") or "",
                translated=getattr(rec, f"translated_{field}") or "",
                target_language=language_code,
                allowlist=allowlist,
            )
            if found:
                hits[(rec.id, field)] = [item.token for item in found]
    return hits


def _apply_foundry_residual_rework(
    *,
    db: Session,
    job: LocalizationJob,
    record_rows: list[LocalizationRecord],
    residual_hits: dict[tuple[uuid.UUID, str], list[str]],
    language_code: str,
    translator_code: str,
    glossary_preserve: tuple[str, ...],
    glossary_allow: frozenset[str],
    quality_v2: bool,
    allow_english_terms: list[str] | None = None,
    previous_answer_rejected: bool = False,
) -> tuple[int, dict[tuple[uuid.UUID, str], list[str]], int, int]:
    """Rework only fields with leftover English. Returns updated count, remaining hits, tokens."""
    if not residual_hits:
        return 0, {}, 0, 0
    settings = get_settings()
    concurrency = max(1, settings.goals_foundry_concurrency)
    rework_qa = build_semantic_qa_service(
        FoundryRateGate(settings.goals_foundry_tokens_per_minute)
    )
    preserve_list = list(glossary_preserve)
    records_by_id = {rec.id: rec for rec in record_rows}
    updated = 0

    def _rework(item: tuple[uuid.UUID, str, list[str]]) -> tuple[uuid.UUID, str, str]:
        record_id, field_name, phrases = item
        rec = records_by_id[record_id]
        source_text = getattr(rec, f"source_{field_name}") or ""
        translated_text = getattr(rec, f"translated_{field_name}") or ""
        result = rework_qa.rework_residual_english(
            field=field_name,  # type: ignore[arg-type]
            target_language=language_code,
            source_text=source_text,
            translated_text=translated_text,
            untranslated_phrases=phrases,
            preserve_terms=preserve_list,
            allow_english_terms=allow_english_terms,
            previous_answer_rejected=previous_answer_rejected,
        )
        repaired = repair_translation(
            source_text,
            result.corrected_text,
            translator_code,
            glossary_preserve,
        )
        return record_id, field_name, repaired

    work_items = [
        (record_id, field_name, phrases)
        for (record_id, field_name), phrases in residual_hits.items()
    ]
    pool = ThreadPoolExecutor(max_workers=concurrency)
    try:
        futures = {pool.submit(_rework, item): item for item in work_items}
        for future in as_completed(futures):
            record_id, field_name, _phrases = futures[future]
            try:
                _rid, field_name, repaired = future.result()
            except FoundryProviderError as exc:
                logger.warning(
                    "residual_english_rework_skipped job_id=%s record=%s field=%s error=%s",
                    job.id,
                    record_id,
                    field_name,
                    str(exc)[:200],
                )
                log_job_event(
                    job,
                    f"Foundry residual rework skipped for {field_name}: {str(exc)[:160]}",
                    "warning",
                )
                continue
            rec = records_by_id[record_id]
            if repaired.strip():
                setattr(rec, f"translated_{field_name}", repaired)
                updated += 1
                db.add(
                    LocalizationQAResult(
                        job_id=job.id,
                        record_id=rec.id,
                        tenant_id=job.tenant_id,
                        field_name=field_name,
                        issue_type="RESIDUAL_ENGLISH_REWORK",
                        severity="LOW",
                        original_text=getattr(rec, f"source_{field_name}"),
                        translated_text=repaired,
                        explanation="Foundry translated leftover ordinary English.",
                    )
                )
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    _apply_quality_repairs(
        record_rows, language_code=language_code, quality_v2=quality_v2
    )
    remaining = _scan_residual_english(
        record_rows, language_code=language_code, allowlist=glossary_allow
    )
    return updated, remaining, rework_qa.input_tokens, rework_qa.output_tokens


def log_job_event(job: LocalizationJob, message: str, level: str = "info") -> None:
    """Append to the job activity log. The caller commits."""
    events = list(job.events or [])
    now = datetime.now(UTC).isoformat()
    last = events[-1] if events else None
    if last and last.get("message") == message and last.get("level") == level:
        merged = dict(last)
        count = merged.get("count")
        merged["count"] = (count if isinstance(count, int) else 1) + 1
        merged["at"] = now
        events[-1] = merged
    else:
        events.append(
            {"at": now, "level": level, "stage": job.current_stage, "message": message}
        )
    job.events = events[-MAX_JOB_EVENTS:]
    flag_modified(job, "events")


def _ensure_not_cancelled(db: Session, job: LocalizationJob) -> None:
    # Read the committed status; pending local changes must not mask a cancel.
    with db.no_autoflush:
        current = db.execute(
            select(LocalizationJob.status).where(LocalizationJob.id == job.id)
        ).scalar_one_or_none()
    if current == LocalizationJobStatus.cancelled:
        raise LocalizationCancelled()
    now = time.monotonic()
    if now - _last_heartbeat.get(job.id, 0.0) >= 30:
        _last_heartbeat[job.id] = now
        renew_outbox_lease(db, aggregate_id=job.id)


def _set_stage(
    db: Session,
    job: LocalizationJob,
    stage: str,
    status: str,
    detail: str = "",
    *,
    log: bool = True,
    check_cancel: bool = True,
) -> None:
    """Persist stage progress immediately so the UI can poll live updates."""
    if check_cancel:
        _ensure_not_cancelled(db, job)
    progress = dict(job.stage_progress or {})
    now_iso = datetime.now(UTC).isoformat()
    previous = progress.get(stage)
    started_at = now_iso
    if isinstance(previous, dict) and previous.get("status") == "running" and status != "queued":
        started_at = str(previous.get("started_at") or previous.get("updated_at") or now_iso)
    progress[stage] = {
        "status": status,
        "detail": detail,
        "started_at": started_at,
        "updated_at": now_iso,
    }
    job.stage_progress = progress
    job.current_stage = stage
    flag_modified(job, "stage_progress")
    if log:
        verb = {"running": "started"}.get(status, status)
        level = {"completed": "success", "failed": "error"}.get(status, "info")
        message = f"{STAGE_NAMES.get(stage, stage)} {verb}"
        if detail:
            message += f": {detail}"
        log_job_event(job, message, level)
    db.commit()
    db.refresh(job)


def _allow_english_terms(glossary: Any) -> list[str]:
    """Terms the tenant marked "Allow English" (Preserve terms are sent separately)."""
    return sorted(
        (term.term for term in glossary.terms if term.action == "allow"), key=str.lower
    )


def _apply_nl_quality_v2_to_records(records: list[LocalizationRecord]) -> None:
    for rec in records:
        rec.translated_goal = apply_nl_quality_v2(
            source=rec.source_goal or "", translated=rec.translated_goal or ""
        )
        rec.translated_description = apply_nl_quality_v2(
            source=rec.source_description or "",
            translated=rec.translated_description or "",
        )
        rec.translated_kra = apply_nl_quality_v2(
            source=rec.source_kra or "", translated=rec.translated_kra or ""
        )


def _apply_quality_v2_to_records(
    records: list[LocalizationRecord], *, language_code: str
) -> None:
    """Language-agnostic v2: numbered measures + deadline/pipe repair."""
    for rec in records:
        for field in ("goal", "description", "kra"):
            setattr(
                rec,
                f"translated_{field}",
                repair_translation(
                    getattr(rec, f"source_{field}") or "",
                    getattr(rec, f"translated_{field}") or "",
                    language_code,
                    restore_measures=True,
                ),
            )


def _apply_quality_repairs(
    records: list[LocalizationRecord], *, language_code: str, quality_v2: bool
) -> None:
    if not quality_v2:
        return
    if language_code == "nl":
        _apply_nl_quality_v2_to_records(records)
    else:
        _apply_quality_v2_to_records(records, language_code=language_code)


def process_localization_job(
    db: Session, *, job_id: uuid.UUID, storage: BlobStorage | None = None
) -> LocalizationJob:
    # The pipeline commits often for live progress. Expiring thousands of loaded records
    # on each commit forces one reload query per record, which stalls large files.
    previous = db.expire_on_commit
    db.expire_on_commit = False
    try:
        return _run_localization_job(db, job_id=job_id, storage=storage)
    finally:
        db.expire_on_commit = previous


def _run_localization_job(
    db: Session, *, job_id: uuid.UUID, storage: BlobStorage | None = None
) -> LocalizationJob:
    settings = get_settings()
    storage = storage or BlobStorage()
    job = db.get(LocalizationJob, job_id)
    if job is None:
        raise ValueError("Localization job not found.")
    if job.status in {
        LocalizationJobStatus.completed,
        LocalizationJobStatus.cancelled,
    }:
        return job

    try:
        language = resolve_language(job.target_language)
        options = dict(job.options or {})
        qa_mode = resolve_qa_mode(str(options.get("qa_mode") or "classic"))
        reuse_translation = bool(options.get("reuse_translation"))
        # Historical option name; quality v2 structural repairs apply to every language.
        # Dutch still gets NL-specific stacked-deadline / Losen handling on top.
        quality_v2 = bool(options.get("nl_quality_v2") or options.get("quality_v2"))
        nl_quality_v2 = quality_v2 and language.code == "nl"
        glossary = load_glossary(db, job.tenant_id)
        storage.ensure_container(CONTAINER)
        log_job_event(
            job,
            f"Worker picked up {job.source_filename} → {language.name} "
            f"({'Foundry' if qa_mode == 'foundry' else 'Classic'} mode, "
            f"{len(glossary.preserve)} Preserve terms).",
        )

        # 1. File validation / load English CSV (+ generated workbook copy)
        job.error_message = None
        job.completed_at = None
        job.status = LocalizationJobStatus.validating
        _set_stage(db, job, "file_validation", "running", f"qa_mode={qa_mode}")
        db.flush()
        source_bytes = storage.download_bytes(container=CONTAINER, blob_name=job.source_blob_name)
        if job.template_blob_name:
            template_bytes = storage.download_bytes(
                container=CONTAINER, blob_name=job.template_blob_name
            )
        else:
            template_bytes = b""
        _set_stage(db, job, "file_validation", "completed")

        # 2. English extraction
        job.status = LocalizationJobStatus.validating
        _set_stage(db, job, "english_extraction", "running")
        db.flush()
        sources = read_english_csv(source_bytes)
        job.total_records = len(sources)
        _set_stage(db, job, "english_extraction", "completed", f"{len(sources)} records")

        # 3. Ensure workbook exists as a 1:1 copy of English (generate if missing)
        job.status = LocalizationJobStatus.reconciling
        _set_stage(db, job, "record_reconciliation", "running")
        db.flush()
        if not template_bytes:
            template_bytes = build_workbook_from_sources(sources, language_code="en")
            template_blob = f"{job.tenant_id}/{job.id}/template/Goals_en.xlsx"
            storage.upload_bytes(
                container=CONTAINER,
                blob_name=template_blob,
                data=template_bytes,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            job.template_blob_name = template_blob
            job.template_filename = "Goals_en.xlsx"
        template = read_template_workbook(template_bytes)
        if len(template.records) != len(sources):
            # Rebuild so row mapping stays identity with English CSV order.
            template_bytes = build_workbook_from_sources(sources, language_code="en")
            template_blob = f"{job.tenant_id}/{job.id}/template/Goals_en.xlsx"
            storage.upload_bytes(
                container=CONTAINER,
                blob_name=template_blob,
                data=template_bytes,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            job.template_blob_name = template_blob
            job.template_filename = "Goals_en.xlsx"
            template = read_template_workbook(template_bytes)
        _set_stage(
            db,
            job,
            "record_reconciliation",
            "completed",
            f"{len(sources)} records copied into workbook",
        )

        # Persist records (1:1 with English source rows; Excel data starts at row 2)
        # QA rows reference records — delete children first (safe on job retries).
        # Reuse jobs already have translated records copied from the parent; keep them.
        db.execute(delete(LocalizationQAResult).where(LocalizationQAResult.job_id == job.id))
        record_rows: list[LocalizationRecord] = []
        if reuse_translation:
            record_rows = list(
                db.scalars(
                    select(LocalizationRecord)
                    .where(LocalizationRecord.job_id == job.id)
                    .order_by(LocalizationRecord.template_row_index)
                )
            )
            if len(record_rows) != len(sources):
                raise ValueError(
                    "Reuse translation failed: parent translations do not match source rows."
                )
        else:
            db.execute(delete(LocalizationRecord).where(LocalizationRecord.job_id == job.id))
            for offset, source in enumerate(sources):
                record = LocalizationRecord(
                    job_id=job.id,
                    tenant_id=job.tenant_id,
                    source_record_key=source.record_key,
                    template_row_index=offset + 2,
                    source_goal=source.goal,
                    source_description=source.description,
                    source_kra=source.kra,
                    technical_fields=source.technical,
                )
                db.add(record)
                record_rows.append(record)
            db.flush()

        # 4. Translation (skipped when reusing a previous job's Translator output)
        job.status = LocalizationJobStatus.translating
        _set_stage(db, job, "translation", "running", language.name)
        db.flush()
        if reuse_translation:
            for rec in record_rows:
                rec.translation_status = LocalizationRecordStatus.translated
            job.cost_estimate = {
                "translator_characters_sent": 0,
                "translator_cache_hits": 0,
                "reused_translation": True,
                "parent_job_id": str(options.get("parent_job_id") or ""),
            }
            translation_detail = "Reused existing translation (Translator skipped)"
            log_job_event(job, "Skipped Azure Translator; reusing copied translations.")
        elif language.translate:
            client = build_translator_client(
                endpoint=settings.azure_translator_endpoint,
                api_key=settings.azure_translator_key,
                region=settings.azure_translator_region,
                batch_size=settings.goals_localization_translate_batch_size,
                chars_per_minute=settings.goals_localization_translator_chars_per_minute,
                paid_endpoint=settings.azure_translator_paid_endpoint,
                paid_key=settings.azure_translator_paid_key,
                paid_region=settings.azure_translator_paid_region,
                paid_fallback=paid_translator_enabled(db, job.tenant_id),
                paid_only=settings.azure_translator_paid_only,
            )
            def _translator_event(level: str, message: str) -> None:
                _ensure_not_cancelled(db, job)
                log_job_event(job, message, level)
                db.commit()

            client.set_notify(_translator_event)
            if settings.azure_translator_paid_only:
                log_job_event(job, "Using the paid Translator only (free key skipped).")
            elif client.fallback is not None:
                log_job_event(job, "Paid Translator fallback is on for this job.")
            translator = CachedTranslator(client, db, tenant_id=job.tenant_id)
            payload = [
                {
                    "id": str(rec.id),
                    "goal": rec.source_goal,
                    "description": rec.source_description,
                    "kra": rec.source_kra,
                }
                for rec in record_rows
            ]
            total_rows = max(1, len(record_rows))
            logged_bucket = {"value": -1}

            def _row_progress(count: int) -> None:
                _ensure_not_cancelled(db, job)
                job.processed_records = count
                percent = int(count * 100 / total_rows)
                if percent // 10 != logged_bucket["value"]:
                    logged_bucket["value"] = percent // 10
                    log_job_event(
                        job, f"Translated {count:,} of {len(record_rows):,} rows ({percent}%)."
                    )
                db.commit()

            translated = translator.translate_fields(
                records=payload,
                to_language=language.azure_translator_code,
                preserve_terms=glossary.preserve,
                glossary_version=glossary.cache_version,
                on_progress=_row_progress,
            )
            for rec in record_rows:
                fields = translated[str(rec.id)]
                rec.translated_goal = fields["goal"]
                rec.translated_description = fields["description"]
                rec.translated_kra = fields["kra"]
                rec.translation_status = LocalizationRecordStatus.translated
            job.cost_estimate = {
                "translator_characters_sent": translator.characters_sent,
                "translator_cache_hits": translator.cache_hits,
            }
            log_job_event(
                job,
                f"Translator sent {translator.characters_sent:,} characters; "
                f"{translator.cache_hits:,} fields reused from cache.",
            )
            translation_detail = "Protected terminology + Azure Translator"
        else:
            for rec in record_rows:
                rec.translated_goal = rec.source_goal
                rec.translated_description = rec.source_description
                rec.translated_kra = rec.source_kra
                rec.translation_status = LocalizationRecordStatus.translated
            job.cost_estimate = {
                "translator_characters_sent": 0,
                "translator_cache_hits": 0,
            }
            translation_detail = "English source copied; workbook code set to en"
        job.processed_records = len(record_rows)
        _set_stage(db, job, "translation", "completed", translation_detail)

        if quality_v2:
            _apply_quality_repairs(
                record_rows, language_code=language.code, quality_v2=True
            )
            log_job_event(
                job,
                "Applied quality fixes (v2) after translation"
                + (" (Dutch-specific)." if nl_quality_v2 else "."),
            )
            db.flush()

        # 5-6 Semantic QA + correction (Foundry mode only)
        unresolved_high = 0
        corrected_count = 0
        if qa_mode == "classic":
            for rec in record_rows:
                rec.qa_status = "classic_pass"
                rec.translation_status = LocalizationRecordStatus.qa_pass
            _set_stage(
                db,
                job,
                "semantic_qa",
                "completed",
                "Skipped — classic mode (Translator + Python QA)",
            )
            _set_stage(
                db,
                job,
                "automatic_correction",
                "completed",
                "Skipped — human review for semantic accuracy",
            )
            job.cost_estimate = {
                **dict(job.cost_estimate or {}),
                "semantic_qa_input_tokens": 0,
                "semantic_qa_output_tokens": 0,
                "qa_mode": qa_mode,
            }
        else:
            job.status = LocalizationJobStatus.semantic_qa
            _set_stage(db, job, "semantic_qa", "running")
            db.flush()
            concurrency = max(1, settings.goals_foundry_concurrency)
            qa = build_semantic_qa_service(
                FoundryRateGate(settings.goals_foundry_tokens_per_minute)
            )
            semantic_prompt, _custom = load_semantic_prompt(db, job.tenant_id)
            _set_stage(db, job, "automatic_correction", "running")
            review_total = len(record_rows)
            log_job_event(
                job,
                f"Foundry is reviewing {review_total:,} rows for meaning "
                f"({concurrency} requests in parallel).",
            )
            skipped_rows = 0
            review_bucket = -1
            preserve_list = list(glossary.preserve)
            allow_english_list = _allow_english_terms(glossary)

            def _review(texts: dict[str, str]) -> Any:
                # Runs in a pool thread: Foundry HTTP only, no ORM or database access.
                return qa.revise_record(
                    target_language=language.code,
                    preserve_terms=preserve_list,
                    allow_english_terms=allow_english_list,
                    system_prompt=semantic_prompt,
                    **texts,
                )

            pool = ThreadPoolExecutor(max_workers=concurrency)
            try:
                futures = {
                    pool.submit(
                        _review,
                        {
                            "source_goal": rec.source_goal or "",
                            "source_description": rec.source_description or "",
                            "source_kra": rec.source_kra or "",
                            "translated_goal": rec.translated_goal or "",
                            "translated_description": rec.translated_description or "",
                            "translated_kra": rec.translated_kra or "",
                        },
                    ): rec
                    for rec in record_rows
                }
                reviewed = 0
                for future in as_completed(futures):
                    rec = futures[future]
                    reviewed += 1
                    try:
                        revision = future.result()
                    except FoundryProviderError as exc:
                        # Do not block the whole worker queue on one rate-limited record.
                        logger.warning(
                            "semantic_revision_skipped job_id=%s record=%s error=%s",
                            job.id,
                            rec.source_record_key,
                            str(exc)[:200],
                        )
                        rec.qa_status = "needs_human_review"
                        rec.translation_status = LocalizationRecordStatus.needs_human_review
                        unresolved_high += 1
                        skipped_rows += 1
                        log_job_event(
                            job,
                            f"Foundry skipped row {rec.source_record_key}: {str(exc)[:160]}",
                            "warning",
                        )
                        db.add(
                            LocalizationQAResult(
                                job_id=job.id,
                                record_id=rec.id,
                                tenant_id=job.tenant_id,
                                field_name="goal",
                                issue_type="FOUNDRY_UNAVAILABLE",
                                severity="HIGH",
                                original_text=rec.source_goal,
                                translated_text=rec.translated_goal,
                                explanation=(
                                    "Semantic revision skipped due to Foundry error: "
                                    f"{str(exc)[:300]}"
                                ),
                            )
                        )
                    else:
                        changed_fields = 0
                        for field_name in ("goal", "description", "kra"):
                            revised = getattr(revision, field_name)
                            if not revised.changed:
                                continue
                            source_text = getattr(rec, f"source_{field_name}")
                            current = repair_translation(
                                source_text,
                                revised.text,
                                language.azure_translator_code,
                                glossary.preserve,
                            )
                            if source_text.strip() and not current.strip():
                                continue
                            setattr(rec, f"translated_{field_name}", current)
                            changed_fields += 1
                            corrected_count += 1
                            db.add(
                                LocalizationQAResult(
                                    job_id=job.id,
                                    record_id=rec.id,
                                    tenant_id=job.tenant_id,
                                    field_name=field_name,
                                    issue_type="SEMANTIC_REVISION",
                                    severity="LOW",
                                    original_text=source_text,
                                    translated_text=current,
                                    explanation=revised.reason or "Foundry revised the meaning.",
                                )
                            )
                        if changed_fields:
                            rec.translation_status = LocalizationRecordStatus.corrected
                            rec.qa_status = "revised"
                        else:
                            rec.translation_status = LocalizationRecordStatus.qa_pass
                            rec.qa_status = "pass"
                    if reviewed % 10 == 0 or reviewed == review_total:
                        percent = int(reviewed * 100 / max(1, review_total))
                        if percent // 10 != review_bucket:
                            review_bucket = percent // 10
                            log_job_event(
                                job,
                                f"Foundry reviewed {reviewed:,} of {review_total:,} rows "
                                f"({percent}%); {corrected_count} fields revised so far.",
                            )
                        # Commits progress and raises LocalizationCancelled on cancel.
                        _set_stage(
                            db,
                            job,
                            "semantic_qa",
                            "running",
                            f"{reviewed:,}/{review_total:,} rows reviewed",
                            log=False,
                        )
            finally:
                # On cancel or error, drop requests that have not started yet.
                pool.shutdown(wait=False, cancel_futures=True)
            job.cost_estimate = {
                **dict(job.cost_estimate or {}),
                "semantic_qa_input_tokens": qa.input_tokens,
                "semantic_qa_output_tokens": qa.output_tokens,
                "qa_mode": qa_mode,
            }
            log_job_event(
                job,
                f"Foundry finished: {corrected_count} fields revised, {skipped_rows} rows skipped, "
                f"{qa.input_tokens:,} input / {qa.output_tokens:,} output tokens.",
                "warning" if skipped_rows else "info",
            )
            _set_stage(db, job, "semantic_qa", "completed", f"{review_total:,} rows reviewed")
            _set_stage(
                db,
                job,
                "automatic_correction",
                "completed",
                f"{corrected_count} fields corrected",
            )
            if quality_v2:
                _apply_quality_repairs(
                    record_rows, language_code=language.code, quality_v2=True
                )
                log_job_event(
                    job,
                    "Re-applied quality fixes (v2) after Foundry"
                    + (" (Dutch-specific)." if nl_quality_v2 else "."),
                )
                db.flush()

        # 7. Technical validation (independent of Foundry — numbers, dates, terminology)
        job.status = LocalizationJobStatus.technical_qa
        _set_stage(db, job, "technical_validation", "running")
        db.flush()
        blank_goal = blank_desc = blank_kra = 0
        numeric = percent = quarters = dates = 0
        unresolved_terms = 0
        nl_stacked = nl_joined = nl_losen = 0
        english_rework_fields = 0
        residual_hits: dict[tuple[uuid.UUID, str], list[str]] = {}
        for rec in record_rows:
            if rec.source_goal and not rec.translated_goal:
                blank_goal += 1
            if rec.source_description and not rec.translated_description:
                blank_desc += 1
            if rec.source_kra and not rec.translated_kra:
                blank_kra += 1
            for field in ("goal", "description", "kra"):
                source = getattr(rec, f"source_{field}")
                translated = getattr(rec, f"translated_{field}")
                for issue in compare_numeric_fields(source, translated):
                    if issue.kind == "NUMERIC_DISCREPANCY":
                        if any(v.endswith("%") for v in issue.source_values + issue.target_values):
                            percent += 1
                        else:
                            numeric += 1
                    elif issue.kind == "QUARTER_DISCREPANCY":
                        quarters += 1
                    elif issue.kind == "DATE_DISCREPANCY":
                        dates += 1
                    db.add(
                        LocalizationQAResult(
                            job_id=job.id,
                            record_id=rec.id,
                            tenant_id=job.tenant_id,
                            field_name=field,
                            issue_type=issue.kind,
                            severity="HIGH",
                            original_text=source,
                            translated_text=translated,
                            explanation=issue.message,
                        )
                    )
                missing_terms = verify_preserved_terms(
                    source=source, translated=translated, terms=glossary.preserve
                )
                for term in missing_terms:
                    unresolved_terms += 1
                    db.add(
                        LocalizationQAResult(
                            job_id=job.id,
                            record_id=rec.id,
                            tenant_id=job.tenant_id,
                            field_name=field,
                            issue_type="TERMINOLOGY_MISSING",
                            severity="HIGH",
                            original_text=source,
                            translated_text=translated,
                            explanation=f"Preserved term missing after translation: {term}",
                        )
                    )
                hits = detect_residual_english(
                    field=field,
                    source=source or "",
                    translated=translated or "",
                    target_language=language.code,
                    allowlist=glossary.allow,
                )
                if hits:
                    residual_hits[(rec.id, field)] = [hit.token for hit in hits]

        # Foundry second pass: translate ordinary English leftovers (all languages).
        if qa_mode == "foundry" and residual_hits:
            before_count = sum(len(phrases) for phrases in residual_hits.values())
            log_job_event(
                job,
                f"Foundry residual-English rework: {len(residual_hits)} fields "
                f"({before_count} phrases) still contain leftover English.",
            )
            _set_stage(
                db,
                job,
                "automatic_correction",
                "running",
                f"Reworking {len(residual_hits)} fields with leftover English",
            )
            (
                english_rework_fields,
                residual_hits,
                rework_in,
                rework_out,
            ) = _apply_foundry_residual_rework(
                db=db,
                job=job,
                record_rows=record_rows,
                residual_hits=residual_hits,
                language_code=language.code,
                translator_code=language.azure_translator_code,
                glossary_preserve=glossary.preserve,
                glossary_allow=glossary.allow,
                quality_v2=quality_v2,
                allow_english_terms=_allow_english_terms(glossary),
            )
            corrected_count += english_rework_fields
            job.cost_estimate = {
                **dict(job.cost_estimate or {}),
                "semantic_qa_input_tokens": int(
                    (job.cost_estimate or {}).get("semantic_qa_input_tokens") or 0
                )
                + rework_in,
                "semantic_qa_output_tokens": int(
                    (job.cost_estimate or {}).get("semantic_qa_output_tokens") or 0
                )
                + rework_out,
                "residual_english_rework_fields": english_rework_fields,
            }
            after_count = sum(len(phrases) for phrases in residual_hits.values())
            log_job_event(
                job,
                f"Foundry residual-English rework finished: {english_rework_fields} fields "
                f"updated; {after_count} leftover phrases remain.",
                "warning" if after_count else "info",
            )
            _set_stage(
                db,
                job,
                "automatic_correction",
                "completed",
                f"{english_rework_fields} residual-English fields reworked",
            )

        unresolved_english = 0
        records_by_id = {rec.id: rec for rec in record_rows}
        for (record_id, field_name), phrases in residual_hits.items():
            rec = records_by_id[record_id]
            source = getattr(rec, f"source_{field_name}")
            translated = getattr(rec, f"translated_{field_name}")
            for phrase in phrases:
                unresolved_english += 1
                db.add(
                    LocalizationQAResult(
                        job_id=job.id,
                        record_id=rec.id,
                        tenant_id=job.tenant_id,
                        field_name=field_name,
                        issue_type="UNTRANSLATED_ENGLISH",
                        severity="MEDIUM",
                        original_text=source,
                        translated_text=translated,
                        explanation=f"English phrase left unchanged: '{phrase}'.",
                    )
                )

        for rec in record_rows:
            if nl_quality_v2:
                defects = detect_nl_quality_defects(
                    rec.translated_goal or "",
                    rec.translated_description or "",
                    rec.translated_kra or "",
                )
                nl_stacked += defects.stacked_deadlines
                nl_joined += defects.joined_kra_numbers
                nl_losen += defects.losen_errors
                if defects.total:
                    rec.translation_status = LocalizationRecordStatus.needs_human_review
        technical_detail = (
            f"{numeric + percent} number, {quarters + dates} date/quarter, "
            f"{unresolved_terms} terminology, {unresolved_english} untranslated-English issues"
        )
        if english_rework_fields:
            technical_detail += f"; reworked {english_rework_fields} residual-English fields"
        if nl_quality_v2:
            technical_detail += (
                f"; Dutch v2: {nl_stacked} stacked deadlines, "
                f"{nl_joined} joined KRA numbers, {nl_losen} Losen"
            )
        _set_stage(db, job, "technical_validation", "completed", technical_detail)

        # 8. Special category QA
        _set_stage(db, job, "special_category_validation", "running")
        category_rows = [
            {
                "record_key": rec.source_record_key,
                "category": str((rec.technical_fields or {}).get("Category") or ""),
                "source_goal": rec.source_goal,
                "source_description": rec.source_description,
                "source_kra": rec.source_kra,
                "translated_goal": rec.translated_goal,
                "translated_description": rec.translated_description,
                "translated_kra": rec.translated_kra,
            }
            for rec in record_rows
        ]
        category_result = validate_special_categories(category_rows)
        for cat_issue in category_result.issues:
            match = next(
                (r for r in record_rows if r.source_record_key == cat_issue.record_key), None
            )
            if match is None:
                continue
            db.add(
                LocalizationQAResult(
                    job_id=job.id,
                    record_id=match.id,
                    tenant_id=job.tenant_id,
                    field_name="category",
                    issue_type=cat_issue.code,
                    severity="HIGH",
                    original_text=cat_issue.category,
                    translated_text="",
                    explanation=cat_issue.message,
                )
            )
        _set_stage(db, job, "special_category_validation", "completed")

        # 9. Excel reconstruction
        job.status = LocalizationJobStatus.generating
        _set_stage(db, job, "excel_reconstruction", "running")
        db.flush()
        write_rows = [
            ExcelWriteRow(
                row_index=int(rec.template_row_index or 0),
                goal=rec.translated_goal,
                description=rec.translated_description,
                kra=rec.translated_kra,
            )
            for rec in record_rows
            if rec.template_row_index
        ]
        output_bytes = reconstruct_workbook(
            template_bytes=template_bytes,
            sheet_name=template.sheet_name,
            column_index=template.column_index,
            rows=write_rows,
            language_code=language.sheet_code,
            rtl=language.rtl,
        )
        out_name = (
            f"{job.tenant_id}/{job.id}/{output_filename(language.code)}"
        )
        storage.upload_bytes(
            container=CONTAINER,
            blob_name=out_name,
            data=output_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        job.output_blob_name = out_name
        workbook_ok = True
        _set_stage(
            db,
            job,
            "excel_reconstruction",
            "completed",
            f"{output_filename(language.code)} saved ({len(write_rows):,} rows)",
        )

        # 10. Hard gate
        job.status = LocalizationJobStatus.final_validation
        _set_stage(db, job, "final_hard_gate", "running")
        open_high = db.scalars(
            select(LocalizationQAResult).where(
                LocalizationQAResult.job_id == job.id,
                LocalizationQAResult.severity == "HIGH",
                LocalizationQAResult.reviewer_status == "open",
            )
        ).all()
        summary: dict[str, Any] = {
            "qa_mode": qa_mode,
            "semantic_accuracy": (
                "requires_human_review"
                if qa_mode == "classic"
                else "foundry_assessed"
            ),
            "source_record_count": len(sources),
            "target_record_count": len(template.records),
            "output_record_count": len(record_rows),
            "matched_records": len(record_rows),
            "unmatched_records": 0,
            "duplicate_records": 0,
            "missing_technical_fields": 0,
            "blank_goal_violations": blank_goal,
            "blank_description_violations": blank_desc,
            "blank_kra_violations": blank_kra,
            "numeric_discrepancies": numeric,
            "percentage_discrepancies": percent,
            "quarter_discrepancies": quarters,
            "date_discrepancies": dates,
            "translation_issues": len(open_high),
            "corrected_records": corrected_count,
            "unresolved_issues": len(open_high),
            "unresolved_high_severity_issues": unresolved_high
            + len(
                [
                    i
                    for i in open_high
                    if i.issue_type
                    not in {"UNTRANSLATED_ENGLISH", "TERMINOLOGY_MISSING"}
                ]
            ),
            "unresolved_terminology_issues": unresolved_terms,
            "unresolved_untranslated_english": unresolved_english,
            "residual_english_rework_fields": english_rework_fields,
            "hotel_revenue_growth_qa_pass": category_result.hotel_revenue_pass,
            "operational_productivity_qa_pass": category_result.operational_productivity_pass,
            "workbook_post_save_integrity": workbook_ok,
        }
        if quality_v2:
            summary["quality_v2"] = True
            summary["nl_quality_v2"] = nl_quality_v2
        if nl_quality_v2:
            summary["nl_stacked_deadline_violations"] = nl_stacked
            summary["nl_joined_kra_number_violations"] = nl_joined
            summary["nl_losen_violations"] = nl_losen
        gate = evaluate_hard_gate(summary)
        summary["hard_gate"] = [
            {"name": c.name, "required": c.required, "actual": c.actual, "passed": c.passed}
            for c in gate.checks
        ]
        job.summary = summary
        job.production_ready = gate.production_ready
        job.failed_records = sum(
            1
            for rec in record_rows
            if rec.translation_status == LocalizationRecordStatus.needs_human_review
        )

        issues_payload = [
            {
                "record_id": str(item.record_id),
                "field_name": item.field_name,
                "issue_type": item.issue_type,
                "severity": item.severity,
                "explanation": item.explanation,
                "reviewer_status": item.reviewer_status,
            }
            for item in db.scalars(
                select(LocalizationQAResult).where(LocalizationQAResult.job_id == job.id)
            ).all()
        ]
        report_bytes = build_qa_report(
            job_id=str(job.id),
            target_language=language.code,
            production_ready=job.production_ready,
            summary=summary,
            gate_checks=summary["hard_gate"],
            issues=issues_payload,
            stages=dict(job.stage_progress or {}),
        )
        report_name = f"{job.tenant_id}/{job.id}/qa_report.json"
        storage.upload_bytes(
            container=CONTAINER,
            blob_name=report_name,
            data=report_bytes,
            content_type="application/json",
        )
        job.report_blob_name = report_name

        def _english_gate_failed() -> bool:
            return any(
                check.name == "Unresolved untranslated English" and not check.passed
                for check in gate.checks
            )

        def _refresh_gate_artifacts() -> None:
            nonlocal issues_payload, report_bytes, failed_checks
            failed_checks = [c.name for c in gate.checks if not c.passed]
            job.summary = summary
            job.production_ready = gate.production_ready
            issues_payload = [
                {
                    "record_id": str(item.record_id),
                    "field_name": item.field_name,
                    "issue_type": item.issue_type,
                    "severity": item.severity,
                    "explanation": item.explanation,
                    "reviewer_status": item.reviewer_status,
                }
                for item in db.scalars(
                    select(LocalizationQAResult).where(LocalizationQAResult.job_id == job.id)
                ).all()
            ]
            report_bytes = build_qa_report(
                job_id=str(job.id),
                target_language=language.code,
                production_ready=job.production_ready,
                summary=summary,
                gate_checks=summary["hard_gate"],
                issues=issues_payload,
                stages=dict(job.stage_progress or {}),
            )
            storage.upload_bytes(
                container=CONTAINER,
                blob_name=report_name,
                data=report_bytes,
                content_type="application/json",
            )

        failed_checks = [c.name for c in gate.checks if not c.passed]
        _set_stage(
            db,
            job,
            "final_hard_gate",
            "completed",
            "passed" if gate.production_ready else f"did not pass ({', '.join(failed_checks)})",
        )

        # 11. Up to 2 repair → hard-gate re-check loops for leftover English.
        max_english_repair_attempts = 2
        post_repair_fields = 0
        repair_attempts = 0
        if not _english_gate_failed():
            _set_stage(
                db,
                job,
                "english_issue_repair",
                "completed",
                "Skipped — no untranslated-English hard-gate failure",
            )
        elif qa_mode != "foundry":
            _set_stage(
                db,
                job,
                "english_issue_repair",
                "completed",
                "Skipped — turn on Foundry to auto-repair leftover English rows",
            )
        else:
            _set_stage(
                db,
                job,
                "english_issue_repair",
                "running",
                f"Repair loop 1/{max_english_repair_attempts}",
            )
            while repair_attempts < max_english_repair_attempts and _english_gate_failed():
                repair_attempts += 1
                log_job_event(
                    job,
                    f"English repair attempt {repair_attempts}/{max_english_repair_attempts}: "
                    f"{unresolved_english} leftover phrases.",
                )
                _set_stage(
                    db,
                    job,
                    "english_issue_repair",
                    "running",
                    f"Attempt {repair_attempts}/{max_english_repair_attempts}: "
                    f"repairing {unresolved_english} English leftovers",
                    log=False,
                )
                repair_hits = _scan_residual_english(
                    record_rows, language_code=language.code, allowlist=glossary.allow
                )
                if not repair_hits:
                    break
                (
                    attempt_fields,
                    repair_hits,
                    repair_in,
                    repair_out,
                ) = _apply_foundry_residual_rework(
                    db=db,
                    job=job,
                    record_rows=record_rows,
                    residual_hits=repair_hits,
                    language_code=language.code,
                    translator_code=language.azure_translator_code,
                    glossary_preserve=glossary.preserve,
                    glossary_allow=glossary.allow,
                    quality_v2=quality_v2,
                    allow_english_terms=_allow_english_terms(glossary),
                    # The technical-validation pass already asked once and was not obeyed.
                    previous_answer_rejected=True,
                )
                post_repair_fields += attempt_fields
                corrected_count += attempt_fields
                english_rework_fields += attempt_fields
                job.cost_estimate = {
                    **dict(job.cost_estimate or {}),
                    "semantic_qa_input_tokens": int(
                        (job.cost_estimate or {}).get("semantic_qa_input_tokens") or 0
                    )
                    + repair_in,
                    "semantic_qa_output_tokens": int(
                        (job.cost_estimate or {}).get("semantic_qa_output_tokens") or 0
                    )
                    + repair_out,
                    "residual_english_rework_fields": english_rework_fields,
                    "english_issue_repair_fields": post_repair_fields,
                    "english_issue_repair_attempts": repair_attempts,
                }
                write_rows = [
                    ExcelWriteRow(
                        row_index=int(rec.template_row_index or 0),
                        goal=rec.translated_goal,
                        description=rec.translated_description,
                        kra=rec.translated_kra,
                    )
                    for rec in record_rows
                    if rec.template_row_index
                ]
                output_bytes = reconstruct_workbook(
                    template_bytes=template_bytes,
                    sheet_name=template.sheet_name,
                    column_index=template.column_index,
                    rows=write_rows,
                    language_code=language.sheet_code,
                    rtl=language.rtl,
                )
                storage.upload_bytes(
                    container=CONTAINER,
                    blob_name=out_name,
                    data=output_bytes,
                    content_type=(
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    ),
                )
                db.execute(
                    delete(LocalizationQAResult).where(
                        LocalizationQAResult.job_id == job.id,
                        LocalizationQAResult.issue_type == "UNTRANSLATED_ENGLISH",
                    )
                )
                unresolved_english = 0
                records_by_id = {rec.id: rec for rec in record_rows}
                for (record_id, field_name), phrases in repair_hits.items():
                    rec = records_by_id[record_id]
                    for phrase in phrases:
                        unresolved_english += 1
                        db.add(
                            LocalizationQAResult(
                                job_id=job.id,
                                record_id=rec.id,
                                tenant_id=job.tenant_id,
                                field_name=field_name,
                                issue_type="UNTRANSLATED_ENGLISH",
                                severity="MEDIUM",
                                original_text=getattr(rec, f"source_{field_name}"),
                                translated_text=getattr(rec, f"translated_{field_name}"),
                                explanation=f"English phrase left unchanged: '{phrase}'.",
                            )
                        )
                summary["unresolved_untranslated_english"] = unresolved_english
                summary["corrected_records"] = corrected_count
                summary["residual_english_rework_fields"] = english_rework_fields
                summary["english_issue_repair_fields"] = post_repair_fields
                summary["english_issue_repair_attempts"] = repair_attempts
                gate = evaluate_hard_gate(summary)
                summary["hard_gate"] = [
                    {
                        "name": c.name,
                        "required": c.required,
                        "actual": c.actual,
                        "passed": c.passed,
                    }
                    for c in gate.checks
                ]
                _refresh_gate_artifacts()
                failed_checks = [c.name for c in gate.checks if not c.passed]
                _set_stage(
                    db,
                    job,
                    "final_hard_gate",
                    "completed",
                    (
                        f"passed after English repair attempt {repair_attempts}"
                        if gate.production_ready
                        else (
                            f"re-check {repair_attempts}/{max_english_repair_attempts}: "
                            f"did not pass ({', '.join(failed_checks)})"
                        )
                    ),
                    log=False,
                )
                if not _english_gate_failed():
                    break

            _set_stage(
                db,
                job,
                "english_issue_repair",
                "completed",
                (
                    f"{repair_attempts} attempt(s): updated {post_repair_fields} fields; "
                    f"{unresolved_english} English leftovers remain"
                    if repair_attempts
                    else "No leftover English remained to repair"
                ),
            )
            log_job_event(
                job,
                f"English repair loop finished after {repair_attempts} attempt(s): "
                f"{post_repair_fields} fields updated, {unresolved_english} leftovers remain.",
                "warning" if unresolved_english else "success",
            )

        if gate.production_ready:
            job.status = LocalizationJobStatus.completed
        else:
            # Any hard-gate failure stays Needs Review, even when failed_records is 0.
            job.status = LocalizationJobStatus.needs_review
        job.error_message = None
        job.completed_at = datetime.now(UTC)
        log_job_event(
            job,
            "Job finished. Production-ready Excel is available."
            if gate.production_ready
            else "Job finished. Diagnostic Excel is available; hard gate did not pass.",
            "success" if gate.production_ready else "warning",
        )
        db.flush()
        return job
    except LocalizationCancelled:
        db.rollback()
        db.refresh(job)
        log_job_event(job, "Worker stopped: job was cancelled.", "warning")
        db.commit()
        return job
    except (TranslatorError, Exception) as exc:
        logger.exception("localization_job_failed job_id=%s", job_id)
        db.rollback()
        db.refresh(job)
        if job.status == LocalizationJobStatus.cancelled:
            return job
        job.status = LocalizationJobStatus.failed
        job.error_message = str(exc)[:2000]
        job.production_ready = False
        job.completed_at = datetime.now(UTC)
        log_job_event(job, f"Job failed: {job.error_message[:300]}", "error")
        if job.current_stage:
            _set_stage(
                db,
                job,
                job.current_stage,
                "failed",
                job.error_message,
                log=False,
                check_cancel=False,
            )
        db.flush()
        return job
