from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import AuthContext, DbSession, require_csrf, require_roles
from app.goals_localization.language_config import (
    DEFAULT_QA_MODE,
    MANDATORY_OPTIONS,
    QA_MODES,
    STAGE_ORDER,
    list_languages,
)
from app.integrations.storage import BlobStorage
from app.models.auth import MembershipRole
from app.models.goals_localization import LocalizationJob, LocalizationJobStatus
from app.services.goals_localization import job_service
from app.core.config import get_settings
from app.services.goals_localization.glossary_store import (
    load_glossary,
    paid_translator_enabled,
    save_glossary,
    set_paid_translator_enabled,
)
from app.services.goals_localization.pipeline import CONTAINER

router = APIRouter(prefix="/goals-localization", tags=["goals-localization"])


class PaidTranslatorUpdate(BaseModel):
    enabled: bool


class GlossaryTermIn(BaseModel):
    term: str = Field(min_length=1, max_length=80)
    action: Literal["preserve", "allow"]


class GlossaryUpdate(BaseModel):
    terms: list[GlossaryTermIn] = Field(min_length=1)


class ReviewRequest(BaseModel):
    issue_id: uuid.UUID
    status: Literal["approved", "rejected", "edited"]
    justification: str = Field(min_length=1)
    edited_text: str | None = None


def _storage() -> BlobStorage:
    return BlobStorage()


def _job_payload(job) -> dict[str, object]:
    return {
        "id": str(job.id),
        "status": job.status.value if hasattr(job.status, "value") else str(job.status),
        "target_language": job.target_language,
        "current_stage": job.current_stage,
        "stage_progress": job.stage_progress or {},
        "stages": list(STAGE_ORDER),
        "options": job.options or {key: True for key in MANDATORY_OPTIONS},
        "summary": job.summary or {},
        "total_records": job.total_records,
        "processed_records": job.processed_records,
        "failed_records": job.failed_records,
        "production_ready": job.production_ready,
        "error_message": job.error_message,
        "cost_estimate": job.cost_estimate or {},
        "source_filename": job.source_filename,
        "template_filename": job.template_filename,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/languages")
def get_languages() -> dict[str, object]:
    """Public static config for the localization UI (no secrets)."""
    return {
        "languages": list_languages(),
        "mandatory_options": list(MANDATORY_OPTIONS),
        "stages": list(STAGE_ORDER),
        "qa_modes": list(QA_MODES),
        "default_qa_mode": DEFAULT_QA_MODE,
    }


_ACTIVE_JOBS = (
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


@router.get("/queue")
def get_queue(
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer)),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    jobs = list(
        db.scalars(
            select(LocalizationJob)
            .where(
                LocalizationJob.tenant_id == auth.tenant_id,
                LocalizationJob.status.in_(_ACTIVE_JOBS),
            )
            .order_by(LocalizationJob.created_at.asc())
        )
    )
    processing = next((job for job in jobs if job.status != LocalizationJobStatus.uploaded), jobs[0] if jobs else None)
    waiting = sum(1 for job in jobs if job.status == LocalizationJobStatus.uploaded)
    return {
        "busy": processing is not None and processing.status != LocalizationJobStatus.uploaded,
        "waiting": waiting,
        "active_count": len(jobs),
        "processing": None
        if processing is None or processing.status == LocalizationJobStatus.uploaded
        else {
            "id": str(processing.id),
            "status": processing.status.value,
            "target_language": processing.target_language,
            "source_filename": processing.source_filename,
            "current_stage": processing.current_stage,
            "processed_records": processing.processed_records,
            "total_records": processing.total_records,
        },
    }


@router.get("/translator-fallback")
def get_translator_fallback(
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer)),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    settings = get_settings()
    return {
        "enabled": paid_translator_enabled(db, auth.tenant_id),
        "configured": bool(settings.azure_translator_paid_key and settings.azure_translator_paid_endpoint),
    }


@router.put("/translator-fallback")
def put_translator_fallback(
    payload: PaidTranslatorUpdate,
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    _: Annotated[AuthContext, Depends(require_roles(MembershipRole.tenant_admin))],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    enabled = set_paid_translator_enabled(db, auth.tenant_id, payload.enabled)
    db.commit()
    return {"enabled": enabled}


@router.get("/glossary")
def get_glossary(
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer)),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    snapshot = load_glossary(db, auth.tenant_id)
    return {
        "terms": [{"term": item.term, "action": item.action} for item in snapshot.terms],
    }


@router.put("/glossary")
def put_glossary(
    payload: GlossaryUpdate,
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    _: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter)),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    try:
        snapshot = save_glossary(
            db,
            auth.tenant_id,
            [item.model_dump() for item in payload.terms],
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "terms": [{"term": item.term, "action": item.action} for item in snapshot.terms],
    }


@router.post("/jobs")
async def create_job(
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    _: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter)),
    ],
    target_language: str = Form(...),
    english_csv: UploadFile = File(...),
    qa_mode: str = Form(DEFAULT_QA_MODE),
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    try:
        job = job_service.create_job_from_uploads(
            db,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            target_language=target_language,
            english_filename=english_csv.filename or "goals.csv",
            english_bytes=await english_csv.read(),
            qa_mode=qa_mode,
            storage=_storage(),
        )
        db.commit()
    except job_service.GoalsLocalizationError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Could not create localization job: {exc}") from exc
    return {"job": _job_payload(job)}


@router.get("/jobs/{job_id}")
def get_job(
    job_id: uuid.UUID,
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer)),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    try:
        job = job_service.get_job(db, tenant_id=auth.tenant_id, job_id=job_id)
    except job_service.GoalsLocalizationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {"job": _job_payload(job)}


@router.get("/jobs/{job_id}/progress")
def get_progress(
    job_id: uuid.UUID,
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer)),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    try:
        job = job_service.get_job(db, tenant_id=auth.tenant_id, job_id=job_id)
    except job_service.GoalsLocalizationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {
        "job_id": str(job.id),
        "status": job.status.value if hasattr(job.status, "value") else str(job.status),
        "current_stage": job.current_stage,
        "stage_progress": job.stage_progress or {},
        "stages": list(STAGE_ORDER),
        "processed_records": job.processed_records,
        "total_records": job.total_records,
        "production_ready": job.production_ready,
    }


@router.get("/jobs/{job_id}/report")
def get_report(
    job_id: uuid.UUID,
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter)),
    ],
) -> Response:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    try:
        job = job_service.get_job(db, tenant_id=auth.tenant_id, job_id=job_id)
    except job_service.GoalsLocalizationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    if not job.report_blob_name:
        raise HTTPException(status_code=404, detail="QA report not available yet.")
    data = _storage().download_bytes(container=CONTAINER, blob_name=job.report_blob_name)
    return Response(
        content=data,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="qa_report_{job.id}.json"'},
    )


@router.get("/jobs/{job_id}/download")
def download_workbook(
    job_id: uuid.UUID,
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter)),
    ],
) -> Response:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    try:
        job = job_service.get_job(db, tenant_id=auth.tenant_id, job_id=job_id)
    except job_service.GoalsLocalizationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    if not job.output_blob_name:
        raise HTTPException(status_code=404, detail="Workbook not available yet.")
    data = _storage().download_bytes(container=CONTAINER, blob_name=job.output_blob_name)
    label = "PRODUCTION" if job.production_ready else "NOT_PRODUCTION_READY"
    filename = f"Goals_{job.target_language}_{label}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/jobs/{job_id}/issues")
def list_issues(
    job_id: uuid.UUID,
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter)),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    try:
        issues = job_service.list_open_issues(db, tenant_id=auth.tenant_id, job_id=job_id)
    except job_service.GoalsLocalizationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {
        "issues": [
            {
                "id": str(item.id),
                "record_id": str(item.record_id),
                "field_name": item.field_name,
                "issue_type": item.issue_type,
                "severity": item.severity,
                "original_text": item.original_text,
                "translated_text": item.translated_text,
                "proposed_correction": item.proposed_correction,
                "explanation": item.explanation,
                "reviewer_status": item.reviewer_status,
                "reviewer_justification": item.reviewer_justification,
            }
            for item in issues
        ]
    }


@router.post("/jobs/{job_id}/review")
def review_issue(
    job_id: uuid.UUID,
    payload: ReviewRequest,
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    _: Annotated[AuthContext, Depends(require_roles(MembershipRole.tenant_admin))],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    try:
        issue = job_service.review_issue(
            db,
            tenant_id=auth.tenant_id,
            job_id=job_id,
            issue_id=payload.issue_id,
            reviewer_id=auth.user_id,
            status=payload.status,
            justification=payload.justification,
            edited_text=payload.edited_text,
        )
        db.commit()
    except job_service.GoalsLocalizationError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {
        "issue": {
            "id": str(issue.id),
            "reviewer_status": issue.reviewer_status,
            "reviewer_justification": issue.reviewer_justification,
            "reviewed_at": issue.reviewed_at.isoformat() if issue.reviewed_at else None,
        }
    }
