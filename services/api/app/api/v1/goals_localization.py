from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.api.deps import DbSession, require_csrf, require_roles
from app.core.config import get_settings
from app.goals_localization.language_config import (
    DEFAULT_QA_MODE,
    MANDATORY_OPTIONS,
    QA_MODES,
    STAGE_ORDER,
    list_languages,
)
from app.integrations.email import email_configured
from app.integrations.storage import BlobStorage
from app.models.auth import MembershipRole
from app.models.goals_localization import (
    LocalizationJob,
    LocalizationJobStatus,
    LocalizationQAResult,
    LocalizationRecord,
)
from app.security.auth_context import AuthContext
from app.services.goals_localization import job_service
from app.services.goals_localization.glossary_store import (
    JobEmailSettings,
    default_semantic_prompt,
    load_glossary,
    load_job_email_settings,
    load_semantic_prompt,
    paid_translator_enabled,
    save_glossary,
    save_job_email_settings,
    save_semantic_prompt,
    set_paid_translator_enabled,
)
from app.services.goals_localization.issue_rows import (
    RowIssue,
    build_issue_rows_workbook,
    issue_rows_filename,
)
from app.services.goals_localization.pipeline import CONTAINER

router = APIRouter(prefix="/goals-localization", tags=["goals-localization"])


class PaidTranslatorUpdate(BaseModel):
    enabled: bool


class JobEmailSettingsUpdate(BaseModel):
    enabled: bool
    recipients: list[EmailStr] = Field(default_factory=list, max_length=20)
    events: list[Literal["started", "completed", "needs_review", "failed"]] = Field(
        default_factory=list
    )


class GlossaryTermIn(BaseModel):
    term: str = Field(min_length=1, max_length=80)
    action: Literal["preserve", "allow"]


class GlossaryUpdate(BaseModel):
    terms: list[GlossaryTermIn] = Field(min_length=1)


class SemanticPromptUpdate(BaseModel):
    prompt: str = Field(max_length=200000)


class ReviewRequest(BaseModel):
    issue_id: uuid.UUID
    status: Literal["approved", "rejected", "edited"]
    justification: str = Field(min_length=1)
    edited_text: str | None = None


def _storage() -> BlobStorage:
    return BlobStorage()


def _job_payload(job: LocalizationJob) -> dict[str, object]:
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
        "has_output": bool(job.output_blob_name),
        "has_report": bool(job.report_blob_name),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def _job_list_item(job: LocalizationJob) -> dict[str, object]:
    """Small row for the files list; the full payload is fetched per job."""
    summary = job.summary or {}
    cost = job.cost_estimate or {}
    options = job.options or {}
    return {
        "id": str(job.id),
        "status": job.status.value if hasattr(job.status, "value") else str(job.status),
        "target_language": job.target_language,
        "options": {"qa_mode": options.get("qa_mode")},
        "summary": {
            key: summary.get(key) for key in ("corrected_records", "unresolved_issues")
        },
        "cost_estimate": {"translator_characters_sent": cost.get("translator_characters_sent")},
        "total_records": job.total_records,
        "production_ready": job.production_ready,
        "error_message": job.error_message,
        "source_filename": job.source_filename,
        "has_output": bool(job.output_blob_name),
        "has_report": bool(job.report_blob_name),
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


@router.get("/queue")
def get_queue(
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(
            require_roles(
                MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer
            )
        ),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    jobs = list(
        db.scalars(
            select(LocalizationJob)
            .where(
                LocalizationJob.tenant_id == auth.tenant_id,
                LocalizationJob.status.in_(job_service.ACTIVE_JOB_STATUSES),
            )
            .order_by(LocalizationJob.created_at.asc())
        )
    )
    processing = next((job for job in jobs if job.status != LocalizationJobStatus.uploaded), None)
    waiting = sum(1 for job in jobs if job.status == LocalizationJobStatus.uploaded)
    # One file at a time: any active/waiting job blocks a new start.
    return {
        "busy": len(jobs) > 0,
        "waiting": waiting,
        "active_count": len(jobs),
        "active_job_id": str(jobs[0].id) if jobs else None,
        "processing": None
        if processing is None
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


@router.post("/queue/clear")
def clear_queue(
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    _: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter)),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    cleared = job_service.clear_active_jobs(db, tenant_id=auth.tenant_id)
    db.commit()
    return {
        "cleared": len(cleared),
        "job_ids": [str(job.id) for job in cleared],
    }


@router.get("/translator-fallback")
def get_translator_fallback(
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(
            require_roles(
                MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer
            )
        ),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    settings = get_settings()
    return {
        "enabled": paid_translator_enabled(db, auth.tenant_id),
        "configured": bool(
            settings.azure_translator_paid_key and settings.azure_translator_paid_endpoint
        ),
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


@router.get("/job-emails")
def get_job_emails(
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(
            require_roles(
                MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer
            )
        ),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    preferences = load_job_email_settings(db, auth.tenant_id)
    is_admin = auth.role == MembershipRole.tenant_admin
    return {
        "enabled": preferences.enabled,
        "configured": email_configured(),
        "recipients": preferences.recipients if is_admin else [],
        "events": preferences.events,
    }


@router.put("/job-emails")
def put_job_emails(
    payload: JobEmailSettingsUpdate,
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    _: Annotated[AuthContext, Depends(require_roles(MembershipRole.tenant_admin))],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    saved = save_job_email_settings(
        db,
        auth.tenant_id,
        JobEmailSettings(
            enabled=payload.enabled,
            recipients=[str(address) for address in payload.recipients],
            events=list(payload.events),
        ),
    )
    db.commit()
    return {"enabled": saved.enabled, "recipients": saved.recipients, "events": saved.events}


@router.get("/glossary")
def get_glossary(
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(
            require_roles(
                MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer
            )
        ),
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


@router.get("/prompt")
def get_prompt(
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(
            require_roles(
                MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer
            )
        ),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    prompt, customized = load_semantic_prompt(db, auth.tenant_id)
    return {
        "prompt": prompt,
        "default_prompt": default_semantic_prompt(),
        "customized": customized,
    }


@router.put("/prompt")
def put_prompt(
    payload: SemanticPromptUpdate,
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
        prompt, customized = save_semantic_prompt(db, auth.tenant_id, payload.prompt)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "prompt": prompt,
        "default_prompt": default_semantic_prompt(),
        "customized": customized,
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
        raise HTTPException(
            status_code=500, detail=f"Could not create localization job: {exc}"
        ) from exc
    return {"job": _job_payload(job)}


@router.get("/jobs")
def list_jobs(
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(
            require_roles(
                MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer
            )
        ),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    jobs = job_service.list_jobs(db, tenant_id=auth.tenant_id)
    return {"jobs": [_job_list_item(job) for job in jobs]}


@router.get("/jobs/{job_id}/logs")
def get_job_logs(
    job_id: uuid.UUID,
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(
            require_roles(
                MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer
            )
        ),
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
        "processed_records": job.processed_records,
        "total_records": job.total_records,
        "events": list(job.events or []),
    }


@router.get("/jobs/{job_id}")
def get_job(
    job_id: uuid.UUID,
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(
            require_roles(
                MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer
            )
        ),
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
        Depends(
            require_roles(
                MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer
            )
        ),
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
    return _blob_redirect(
        job.report_blob_name, f"qa_report_{job.id}.json", "application/json"
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
    label = "PRODUCTION" if job.production_ready else "NOT_PRODUCTION_READY"
    return _blob_redirect(
        job.output_blob_name,
        f"Goals_{job.target_language}_{label}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/jobs/{job_id}/issue-rows")
def download_issue_rows(
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
    # Same issues the hard gate counts: open, and not the LOW-severity Foundry revisions.
    rows = db.execute(
        select(LocalizationRecord.template_row_index, LocalizationQAResult)
        .join(LocalizationRecord, LocalizationRecord.id == LocalizationQAResult.record_id)
        .where(
            LocalizationQAResult.job_id == job.id,
            LocalizationQAResult.tenant_id == auth.tenant_id,
            LocalizationQAResult.reviewer_status == "open",
            LocalizationQAResult.severity != "LOW",
        )
    ).all()
    issues_by_row: dict[int, list[RowIssue]] = {}
    for row_index, issue in rows:
        if not row_index:
            continue
        issues_by_row.setdefault(int(row_index), []).append(
            RowIssue(
                field_name=issue.field_name,
                issue_type=issue.issue_type,
                severity=issue.severity,
                explanation=issue.explanation,
            )
        )
    if not issues_by_row:
        raise HTTPException(status_code=404, detail="This job has no open issue rows.")
    storage = _storage()
    data = build_issue_rows_workbook(
        storage.download_bytes(container=CONTAINER, blob_name=job.output_blob_name), issues_by_row
    )
    filename = issue_rows_filename(job.target_language)
    blob_name = f"{job.tenant_id}/{job.id}/{filename}"
    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    storage.upload_bytes(
        container=CONTAINER, blob_name=blob_name, data=data, content_type=content_type
    )
    return _blob_redirect(blob_name, filename, content_type)


def _blob_redirect(blob_name: str, filename: str, content_type: str) -> RedirectResponse:
    # Large files stall when streamed back through the web proxy, so the browser
    # downloads directly from storage with a short-lived read-only link.
    url = _storage().create_download_url(
        container=CONTAINER, blob_name=blob_name, filename=filename, content_type=content_type
    )
    return RedirectResponse(url, status_code=307, headers={"Cache-Control": "no-store"})


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
