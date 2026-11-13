from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, defer
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import get_settings
from app.goals_localization.language_config import (
    MANDATORY_OPTIONS,
    resolve_language,
    resolve_qa_mode,
)
from app.integrations.storage import BlobStorage
from app.models.domain import OutboxEvent
from app.models.goals_localization import (
    LocalizationJob,
    LocalizationJobStatus,
    LocalizationQAResult,
    LocalizationRecord,
    LocalizationRecordStatus,
)
from app.services.goals_localization.csv_reader import read_english_csv
from app.services.goals_localization.excel_generator import build_workbook_from_sources
from app.services.goals_localization.file_validation import (
    FileValidationError,
    validate_english_csv,
)
from app.services.goals_localization.pipeline import CONTAINER, log_job_event

EVENT_TYPE = "goals.localization.run"

ACTIVE_JOB_STATUSES = (
    LocalizationJobStatus.uploaded,
    LocalizationJobStatus.validating,
    LocalizationJobStatus.reconciling,
    LocalizationJobStatus.translating,
    LocalizationJobStatus.semantic_qa,
    LocalizationJobStatus.correcting,
    LocalizationJobStatus.technical_qa,
    LocalizationJobStatus.generating,
    LocalizationJobStatus.final_validation,
)


class GoalsLocalizationError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def tenant_has_active_job(db: Session, *, tenant_id: uuid.UUID) -> LocalizationJob | None:
    return db.scalar(
        select(LocalizationJob)
        .where(
            LocalizationJob.tenant_id == tenant_id,
            LocalizationJob.status.in_(ACTIVE_JOB_STATUSES),
        )
        .order_by(LocalizationJob.created_at.asc())
        .limit(1)
    )


def clear_active_jobs(db: Session, *, tenant_id: uuid.UUID) -> list[LocalizationJob]:
    """Cancel every in-flight / waiting Goals job and drop matching outbox work."""
    jobs = list(
        db.scalars(
            select(LocalizationJob).where(
                LocalizationJob.tenant_id == tenant_id,
                LocalizationJob.status.in_(ACTIVE_JOB_STATUSES),
            )
        )
    )
    if not jobs:
        return []
    now = datetime.now(UTC)
    job_ids = [job.id for job in jobs]
    for job in jobs:
        job.status = LocalizationJobStatus.cancelled
        job.error_message = "Cancelled from the worker queue."
        job.completed_at = now
        progress = {
            stage: (
                {**info, "status": "cancelled"}
                if isinstance(info, dict) and info.get("status") == "running"
                else info
            )
            for stage, info in dict(job.stage_progress or {}).items()
        }
        job.stage_progress = progress
        flag_modified(job, "stage_progress")
        log_job_event(
            job, "Cancelled from the UI. The worker stops at its next checkpoint.", "warning"
        )
    events = list(
        db.scalars(
            select(OutboxEvent).where(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.event_type == EVENT_TYPE,
                OutboxEvent.aggregate_type == "localization_job",
                OutboxEvent.aggregate_id.in_(job_ids),
                OutboxEvent.processed_at.is_(None),
            )
            # The worker holds a lock on the event it is running and marks it itself.
            .with_for_update(skip_locked=True)
        )
    )
    for event in events:
        event.processed_at = now
    db.flush()
    return jobs


def create_job_from_uploads(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    target_language: str,
    english_filename: str,
    english_bytes: bytes,
    qa_mode: str | None = None,
    nl_quality_v2: bool = False,
    storage: BlobStorage | None = None,
) -> LocalizationJob:
    settings = get_settings()
    if tenant_has_active_job(db, tenant_id=tenant_id) is not None:
        raise GoalsLocalizationError(
            "queue_busy",
            "Another Goals file is already in the worker. "
            "Wait for it to finish, or clear the queue first.",
            409,
        )
    try:
        language = resolve_language(target_language)
    except ValueError as exc:
        raise GoalsLocalizationError("invalid_language", str(exc), 400) from exc
    try:
        mode = resolve_qa_mode(qa_mode)
    except ValueError as exc:
        raise GoalsLocalizationError("invalid_qa_mode", str(exc), 400) from exc

    max_bytes = settings.goals_localization_max_upload_mb * 1024 * 1024
    try:
        english = validate_english_csv(
            filename=english_filename, data=english_bytes, max_bytes=max_bytes
        )
    except FileValidationError as exc:
        raise GoalsLocalizationError("invalid_file", str(exc), 400) from exc

    try:
        sources = read_english_csv(english.data)
    except Exception as exc:
        raise GoalsLocalizationError(
            "invalid_file", f"Could not parse English CSV: {exc}", 400
        ) from exc
    if not sources:
        raise GoalsLocalizationError("invalid_file", "English CSV has no goal records.", 400)

    # Copy English structure into a SuccessFactors-style workbook; no separate XLSX upload.
    template_bytes = build_workbook_from_sources(sources, language_code="en")

    storage = storage or BlobStorage()
    storage.ensure_container(CONTAINER)
    job_id = uuid.uuid4()
    source_blob = f"{tenant_id}/{job_id}/source/{english.filename}"
    template_blob = f"{tenant_id}/{job_id}/template/Goals_en.xlsx"
    storage.upload_bytes(
        container=CONTAINER,
        blob_name=source_blob,
        data=english.data,
        content_type=english.content_type,
    )
    storage.upload_bytes(
        container=CONTAINER,
        blob_name=template_blob,
        data=template_bytes,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    options: dict[str, object] = {key: True for key in MANDATORY_OPTIONS}
    options["qa_mode"] = mode
    options["run_semantic_qa"] = mode == "foundry"
    if nl_quality_v2:
        # Option name is historical (started as Dutch-only); applies to all languages.
        options["nl_quality_v2"] = True
    job = LocalizationJob(
        id=job_id,
        tenant_id=tenant_id,
        created_by_user_id=user_id,
        target_language=language.code,
        source_blob_name=source_blob,
        template_blob_name=template_blob,
        source_filename=english.filename,
        template_filename="Goals_en.xlsx",
        status=LocalizationJobStatus.uploaded,
        options=options,
        stage_progress={},
        summary={},
        cost_estimate={},
        events=[],
        total_records=len(sources),
    )
    log_job_event(
        job,
        f"Uploaded {english.filename} ({len(sources):,} rows) for {language.name}. "
        "Waiting for the worker.",
    )
    db.add(job)
    db.add(
        OutboxEvent(
            tenant_id=tenant_id,
            event_type=EVENT_TYPE,
            aggregate_type="localization_job",
            aggregate_id=job.id,
            payload={"job_id": str(job.id), "tenant_id": str(tenant_id)},
        )
    )
    db.flush()
    return job


def create_version_from_job(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    parent_job_id: uuid.UUID,
    qa_mode: str | None = None,
    nl_quality_v2: bool = False,
    storage: BlobStorage | None = None,
) -> LocalizationJob:
    """Create a new job that reuses the parent's translations (no Translator call)."""
    if tenant_has_active_job(db, tenant_id=tenant_id) is not None:
        raise GoalsLocalizationError(
            "queue_busy",
            "Another Goals file is already in the worker. "
            "Wait for it to finish, or clear the queue first.",
            409,
        )
    parent = get_job(db, tenant_id=tenant_id, job_id=parent_job_id)
    if parent.status not in {
        LocalizationJobStatus.completed,
        LocalizationJobStatus.needs_review,
    }:
        raise GoalsLocalizationError(
            "parent_not_ready",
            "Only a completed or needs-review job can be reused for a new version.",
            400,
        )
    parent_records = list(
        db.scalars(
            select(LocalizationRecord)
            .where(
                LocalizationRecord.job_id == parent.id,
                LocalizationRecord.tenant_id == tenant_id,
            )
            .order_by(LocalizationRecord.template_row_index)
        )
    )
    if not parent_records or not any(rec.translated_goal for rec in parent_records):
        raise GoalsLocalizationError(
            "no_translation",
            "This job has no reusable translations yet.",
            400,
        )
    try:
        mode = resolve_qa_mode(qa_mode or str((parent.options or {}).get("qa_mode") or "foundry"))
    except ValueError as exc:
        raise GoalsLocalizationError("invalid_qa_mode", str(exc), 400) from exc
    storage = storage or BlobStorage()
    storage.ensure_container(CONTAINER)
    job_id = uuid.uuid4()
    source_blob = f"{tenant_id}/{job_id}/source/{parent.source_filename}"
    template_blob = f"{tenant_id}/{job_id}/template/{parent.template_filename or 'Goals_en.xlsx'}"
    storage.upload_bytes(
        container=CONTAINER,
        blob_name=source_blob,
        data=storage.download_bytes(container=CONTAINER, blob_name=parent.source_blob_name),
        content_type="text/csv",
    )
    storage.upload_bytes(
        container=CONTAINER,
        blob_name=template_blob,
        data=storage.download_bytes(container=CONTAINER, blob_name=parent.template_blob_name),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    options: dict[str, object] = {key: True for key in MANDATORY_OPTIONS}
    options["qa_mode"] = mode
    options["run_semantic_qa"] = mode == "foundry"
    options["reuse_translation"] = True
    options["parent_job_id"] = str(parent.id)
    if nl_quality_v2:
        options["nl_quality_v2"] = True

    job = LocalizationJob(
        id=job_id,
        tenant_id=tenant_id,
        created_by_user_id=user_id,
        target_language=parent.target_language,
        source_blob_name=source_blob,
        template_blob_name=template_blob,
        source_filename=parent.source_filename,
        template_filename=parent.template_filename,
        status=LocalizationJobStatus.uploaded,
        options=options,
        stage_progress={},
        summary={},
        cost_estimate={},
        events=[],
        total_records=len(parent_records),
    )
    log_job_event(
        job,
        f"New version from job {parent.id}. Reusing {len(parent_records):,} translations "
        f"(Translator skipped). QA mode={mode}"
        + (", quality v2 on." if nl_quality_v2 else "."),
    )
    db.add(job)
    for parent_rec in parent_records:
        db.add(
            LocalizationRecord(
                job_id=job.id,
                tenant_id=tenant_id,
                source_record_key=parent_rec.source_record_key,
                template_row_index=parent_rec.template_row_index,
                source_goal=parent_rec.source_goal,
                source_description=parent_rec.source_description,
                source_kra=parent_rec.source_kra,
                translated_goal=parent_rec.translated_goal,
                translated_description=parent_rec.translated_description,
                translated_kra=parent_rec.translated_kra,
                technical_fields=dict(parent_rec.technical_fields or {}),
                translation_status=LocalizationRecordStatus.translated,
                source_hashes=dict(parent_rec.source_hashes or {}),
            )
        )
    db.add(
        OutboxEvent(
            tenant_id=tenant_id,
            event_type=EVENT_TYPE,
            aggregate_type="localization_job",
            aggregate_id=job.id,
            payload={"job_id": str(job.id), "tenant_id": str(tenant_id)},
        )
    )
    db.flush()
    return job


def list_jobs(db: Session, *, tenant_id: uuid.UUID, limit: int = 50) -> list[LocalizationJob]:
    return list(
        db.scalars(
            select(LocalizationJob)
            .options(defer(LocalizationJob.events))
            .where(LocalizationJob.tenant_id == tenant_id)
            .order_by(LocalizationJob.created_at.desc())
            .limit(limit)
        )
    )


def get_job(db: Session, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> LocalizationJob:
    job = db.scalar(
        select(LocalizationJob).where(
            LocalizationJob.id == job_id, LocalizationJob.tenant_id == tenant_id
        )
    )
    if job is None:
        raise GoalsLocalizationError("not_found", "Localization job not found.", 404)
    return job


def list_open_issues(
    db: Session, *, tenant_id: uuid.UUID, job_id: uuid.UUID
) -> list[LocalizationQAResult]:
    get_job(db, tenant_id=tenant_id, job_id=job_id)
    return list(
        db.scalars(
            select(LocalizationQAResult).where(
                LocalizationQAResult.job_id == job_id,
                LocalizationQAResult.tenant_id == tenant_id,
            )
        )
    )


def review_issue(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    issue_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    status: str,
    justification: str,
    edited_text: str | None = None,
) -> LocalizationQAResult:
    if status not in {"approved", "rejected", "edited"}:
        raise GoalsLocalizationError(
            "invalid_status", "reviewer_status must be approved|rejected|edited."
        )
    if not justification.strip():
        raise GoalsLocalizationError(
            "justification_required", "Reviewer justification is required."
        )
    get_job(db, tenant_id=tenant_id, job_id=job_id)
    issue = db.scalar(
        select(LocalizationQAResult).where(
            LocalizationQAResult.id == issue_id,
            LocalizationQAResult.job_id == job_id,
            LocalizationQAResult.tenant_id == tenant_id,
        )
    )
    if issue is None:
        raise GoalsLocalizationError("not_found", "QA issue not found.", 404)
    issue.reviewer_status = status
    issue.reviewer_id = reviewer_id
    issue.reviewer_justification = justification.strip()
    issue.reviewed_at = datetime.now(UTC)
    if edited_text is not None:
        issue.proposed_correction = edited_text
    db.flush()
    return issue
