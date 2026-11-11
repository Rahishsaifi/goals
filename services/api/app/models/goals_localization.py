from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LocalizationJobStatus(enum.StrEnum):
    uploaded = "UPLOADED"
    validating = "VALIDATING"
    reconciling = "RECONCILING"
    translating = "TRANSLATING"
    semantic_qa = "SEMANTIC_QA"
    correcting = "CORRECTING"
    technical_qa = "TECHNICAL_QA"
    generating = "GENERATING"
    final_validation = "FINAL_VALIDATION"
    completed = "COMPLETED"
    needs_review = "NEEDS_REVIEW"
    failed = "FAILED"
    cancelled = "CANCELLED"


class LocalizationRecordStatus(enum.StrEnum):
    pending = "pending"
    translated = "translated"
    qa_pass = "qa_pass"
    qa_fail = "qa_fail"
    corrected = "corrected"
    needs_human_review = "needs_human_review"
    failed = "failed"


class LocalizationJob(Base):
    __tablename__ = "localization_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    target_language: Mapped[str] = mapped_column(String(32), nullable=False)
    source_blob_name: Mapped[str] = mapped_column(String(500), nullable=False)
    template_blob_name: Mapped[str] = mapped_column(String(500), nullable=False)
    output_blob_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    report_blob_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_filename: Mapped[str] = mapped_column(String(300), nullable=False)
    template_filename: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[LocalizationJobStatus] = mapped_column(
        Enum(LocalizationJobStatus, name="localization_job_status"),
        nullable=False,
        default=LocalizationJobStatus.uploaded,
    )
    current_stage: Mapped[str | None] = mapped_column(String(80), nullable=True)
    stage_progress: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    options: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    summary: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    total_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    production_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_estimate: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    events: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LocalizationRecord(Base):
    __tablename__ = "localization_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("localization_jobs.id"), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    source_record_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    template_row_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_goal: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_kra: Mapped[str] = mapped_column(Text, nullable=False, default="")
    translated_goal: Mapped[str] = mapped_column(Text, nullable=False, default="")
    translated_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    translated_kra: Mapped[str] = mapped_column(Text, nullable=False, default="")
    technical_fields: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    translation_status: Mapped[LocalizationRecordStatus] = mapped_column(
        Enum(LocalizationRecordStatus, name="localization_record_status"),
        nullable=False,
        default=LocalizationRecordStatus.pending,
    )
    qa_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    correction_attempts: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    source_hashes: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)


class LocalizationQAResult(Base):
    __tablename__ = "localization_qa_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("localization_jobs.id"), nullable=False, index=True
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("localization_records.id"), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(40), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    translated_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    proposed_correction: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reviewer_status: Mapped[str] = mapped_column(String(40), nullable=False, default="open")
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewer_justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LocalizationGlossary(Base):
    __tablename__ = "localization_glossaries"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    terms: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False, default=list)
    paid_translator_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    job_emails_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    job_email_recipients: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    job_email_events: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: ["started", "completed", "needs_review", "failed"],
        server_default=text("'[\"started\", \"completed\", \"needs_review\", \"failed\"]'::jsonb"),
    )
    semantic_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TranslationCacheEntry(Base):
    __tablename__ = "translation_cache_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_language: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    glossary_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
