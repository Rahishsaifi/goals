from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.storage import BlobStorage
from app.models.domain import (
    DocumentKind,
    IngestionBatch,
    IngestionBatchItem,
    OutboxEvent,
    ProcessingStatus,
    Resume,
    ResumeVersion,
)

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_BYTES = 10 * 1024 * 1024


class ResumeServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def create_upload_session(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    filename: str,
    content_type: str,
    byte_size: int,
    storage: BlobStorage,
) -> dict[str, object]:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ResumeServiceError("unsupported_type", "Only PDF and DOCX are allowed.")
    if byte_size <= 0 or byte_size > MAX_BYTES:
        raise ResumeServiceError("invalid_size", "File exceeds the allowed size.")
    batch = IngestionBatch(
        tenant_id=tenant_id,
        created_by_user_id=user_id,
        kind=DocumentKind.resume,
        total_items=1,
        status=ProcessingStatus.uploaded,
    )
    db.add(batch)
    db.flush()
    resume = Resume(
        tenant_id=tenant_id,
        created_by_user_id=user_id,
        candidate_label=filename,
        status=ProcessingStatus.uploaded,
    )
    db.add(resume)
    db.flush()
    blob_name = f"{tenant_id}/{resume.id}/{uuid.uuid4()}-{filename}"
    version = ResumeVersion(
        resume_id=resume.id,
        tenant_id=tenant_id,
        version_number=1,
        original_filename=filename,
        content_type=content_type,
        byte_size=byte_size,
        content_hash="pending",
        storage_container="resumes",
        storage_blob_name=blob_name,
        status=ProcessingStatus.uploaded,
    )
    db.add(version)
    db.flush()
    resume.current_version_id = version.id
    item = IngestionBatchItem(
        batch_id=batch.id,
        tenant_id=tenant_id,
        resume_id=resume.id,
        status=ProcessingStatus.uploaded,
    )
    db.add(item)
    grant = storage.create_upload_grant(
        container="resumes", blob_name=blob_name, content_type=content_type
    )
    return {
        "resume_id": resume.id,
        "version_id": version.id,
        "batch_id": batch.id,
        "upload_url": grant.upload_url,
        "expires_at": grant.expires_at,
        "container": grant.container,
        "blob_name": grant.blob_name,
    }


def complete_upload(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    resume_id: uuid.UUID,
    storage: BlobStorage,
) -> Resume:
    resume = db.scalar(
        select(Resume).where(Resume.id == resume_id, Resume.tenant_id == tenant_id)
    )
    if resume is None or resume.deleted_at is not None:
        raise ResumeServiceError("not_found", "Resume not found.", status_code=404)
    version = db.get(ResumeVersion, resume.current_version_id)
    if version is None or version.tenant_id != tenant_id:
        raise ResumeServiceError("not_found", "Resume version not found.", status_code=404)
    content = storage.download_bytes(
        container=version.storage_container, blob_name=version.storage_blob_name
    )
    if len(content) != version.byte_size:
        # Allow small variance only if client estimated; enforce max.
        if len(content) > MAX_BYTES:
            raise ResumeServiceError("invalid_size", "Uploaded object exceeds size limit.")
        version.byte_size = len(content)
    digest = hashlib.sha256(content).hexdigest()
    duplicate = db.scalar(
        select(Resume).where(
            Resume.tenant_id == tenant_id,
            Resume.content_hash == digest,
            Resume.id != resume.id,
            Resume.deleted_at.is_(None),
        )
    )
    if duplicate is not None:
        raise ResumeServiceError("duplicate", "Duplicate document hash in this tenant.")
    version.content_hash = digest
    resume.content_hash = digest
    version.status = ProcessingStatus.queued
    resume.status = ProcessingStatus.queued
    db.add(
        OutboxEvent(
            tenant_id=tenant_id,
            event_type="resume.process",
            aggregate_type="resume_version",
            aggregate_id=version.id,
            payload={
                "resume_id": str(resume.id),
                "version_id": str(version.id),
                "tenant_id": str(tenant_id),
            },
        )
    )
    db.flush()
    return resume


def list_resumes(db: Session, *, tenant_id: uuid.UUID) -> list[Resume]:
    return list(
        db.scalars(
            select(Resume)
            .where(Resume.tenant_id == tenant_id, Resume.deleted_at.is_(None))
            .order_by(Resume.created_at.desc())
        )
    )


def get_resume(db: Session, *, tenant_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    resume = db.scalar(
        select(Resume).where(Resume.id == resume_id, Resume.tenant_id == tenant_id)
    )
    if resume is None or resume.deleted_at is not None:
        raise ResumeServiceError("not_found", "Resume not found.", status_code=404)
    return resume


def soft_delete_resume(db: Session, *, tenant_id: uuid.UUID, resume_id: uuid.UUID) -> None:
    resume = get_resume(db, tenant_id=tenant_id, resume_id=resume_id)
    resume.deleted_at = datetime.now(UTC)
    resume.status = ProcessingStatus.deletion_pending
    db.add(
        OutboxEvent(
            tenant_id=tenant_id,
            event_type="resume.delete",
            aggregate_type="resume",
            aggregate_id=resume.id,
            payload={"resume_id": str(resume.id), "tenant_id": str(tenant_id)},
        )
    )
    db.flush()
