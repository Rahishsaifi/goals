from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.model_provider import ModelProvider
from app.integrations.storage import BlobStorage
from app.models.domain import OutboxEvent, ProcessingStatus, Resume, ResumeVersion
from app.parsers.documents import UnsupportedDocumentError, parse_document
from app.services import usage_service


def claim_outbox_events(db: Session, *, limit: int = 10) -> list[OutboxEvent]:
    events = list(
        db.scalars(
            select(OutboxEvent)
            .where(
                OutboxEvent.processed_at.is_(None),
                OutboxEvent.available_at <= datetime.now(UTC),
            )
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    now = datetime.now(UTC)
    for event in events:
        event.locked_at = now
        event.attempt_count += 1
    db.flush()
    return events


def process_resume_version(
    db: Session,
    *,
    version_id: uuid.UUID,
    storage: BlobStorage,
    provider: ModelProvider,
) -> None:
    version = db.get(ResumeVersion, version_id)
    if version is None:
        return
    resume = db.get(Resume, version.resume_id)
    if resume is None:
        return
    version.status = ProcessingStatus.extracting_text
    resume.status = ProcessingStatus.extracting_text
    db.flush()
    try:
        content = storage.download_bytes(
            container=version.storage_container, blob_name=version.storage_blob_name
        )
        parsed = parse_document(
            content=content,
            content_type=version.content_type,
            filename=version.original_filename,
        )
        version.extracted_text = parsed.text
        version.parser_version = parsed.parser_version
        version.status = ProcessingStatus.normalizing_profile
        resume.status = ProcessingStatus.normalizing_profile
        db.flush()
        extracted = provider.extract_resume_profile(parsed.text)
        usage_service.record_usage(
            db,
            tenant_id=version.tenant_id,
            operation_type="resume_extraction",
            provider=provider.name,
            usage=extracted.usage,
            idempotency_key=f"resume-extract-{version.id}",
            resume_id=resume.id,
        )
        profile = extracted.value
        version.extracted_profile = profile.model_dump()
        if profile.full_name:
            resume.candidate_label = profile.full_name[:200]
        version.status = ProcessingStatus.ready
        resume.status = ProcessingStatus.ready
    except UnsupportedDocumentError:
        version.status = ProcessingStatus.failed
        resume.status = ProcessingStatus.failed
        version.error_code = "unsupported_document"
        version.extracted_text = None
    except Exception as exc:
        # Unreadable / missing blobs will not succeed on retry — surface as failed.
        name = type(exc).__name__
        permanent = name in {
            "PdfReadError",
            "ResourceNotFoundError",
            "BadZipFile",
            "PackageNotFoundError",
        } or "startxref" in str(exc).lower() or "blob does not exist" in str(exc).lower()
        if permanent:
            version.status = ProcessingStatus.failed
            resume.status = ProcessingStatus.failed
            version.error_code = "unreadable_document"
            version.extracted_text = None
        else:
            version.status = ProcessingStatus.retry_pending
            resume.status = ProcessingStatus.retry_pending
            version.error_code = "processing_failed"
    db.flush()


def mark_processed(db: Session, event: OutboxEvent) -> None:
    event.processed_at = datetime.now(UTC)
    db.flush()
