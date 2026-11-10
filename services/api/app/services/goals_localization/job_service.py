from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.goals_localization.language_config import (
    MANDATORY_OPTIONS,
    resolve_language,
    resolve_qa_mode,
)
from app.integrations.storage import BlobStorage
from app.models.domain import OutboxEvent
from app.models.goals_localization import LocalizationJob, LocalizationJobStatus, LocalizationQAResult
from app.services.goals_localization.csv_reader import read_english_csv
from app.services.goals_localization.excel_generator import build_workbook_from_sources
from app.services.goals_localization.file_validation import (
    FileValidationError,
    validate_english_csv,
)
from app.services.goals_localization.pipeline import CONTAINER

EVENT_TYPE = "goals.localization.run"


class GoalsLocalizationError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def create_job_from_uploads(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    target_language: str,
    english_filename: str,
    english_bytes: bytes,
    qa_mode: str | None = None,
    storage: BlobStorage | None = None,
) -> LocalizationJob:
    settings = get_settings()
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
        raise GoalsLocalizationError("invalid_file", f"Could not parse English CSV: {exc}", 400) from exc
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

    options = {key: True for key in MANDATORY_OPTIONS}
    options["qa_mode"] = mode
    options["run_semantic_qa"] = mode == "foundry"
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
        total_records=len(sources),
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


def get_job(db: Session, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> LocalizationJob:
    job = db.scalar(
        select(LocalizationJob).where(
            LocalizationJob.id == job_id, LocalizationJob.tenant_id == tenant_id
        )
    )
    if job is None:
        raise GoalsLocalizationError("not_found", "Localization job not found.", 404)
    return job


def list_open_issues(db: Session, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> list[LocalizationQAResult]:
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
        raise GoalsLocalizationError("invalid_status", "reviewer_status must be approved|rejected|edited.")
    if not justification.strip():
        raise GoalsLocalizationError("justification_required", "Reviewer justification is required.")
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
