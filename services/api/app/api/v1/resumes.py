from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import DbSession, require_csrf, require_roles
from app.integrations.storage import BlobStorage
from app.models.auth import MembershipRole
from app.models.domain import ResumeVersion
from app.security.auth_context import AuthContext
from app.services import resume_service
from app.services.resume_service import ResumeServiceError

router = APIRouter(prefix="/resumes", tags=["resumes"])

ALLOWED_UPLOAD_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class UploadSessionRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str
    byte_size: int = Field(gt=0)


class CompleteUploadRequest(BaseModel):
    resume_id: uuid.UUID


def _storage() -> BlobStorage:
    return BlobStorage()


def _resolve_content_type(filename: str, content_type: str | None) -> str:
    if content_type in ALLOWED_UPLOAD_TYPES:
        return content_type
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return content_type or "application/octet-stream"


@router.post("/upload")
async def upload_resume(
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    _: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter)),
    ],
    file: UploadFile = File(...),
    filename: str | None = Form(default=None),
) -> dict[str, object]:
    """Browser-friendly upload that writes through the API (avoids Azurite CORS)."""
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    original_name = (filename or file.filename or "resume.pdf").strip()
    content_type = _resolve_content_type(original_name, file.content_type)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")
    storage = _storage()
    try:
        session = resume_service.create_upload_session(
            db,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            filename=original_name,
            content_type=content_type,
            byte_size=len(data),
            storage=storage,
        )
        version = db.get(ResumeVersion, session["version_id"])
        if version is None:
            raise ResumeServiceError("not_found", "Resume version not found.", 404)
        storage.upload_bytes(
            container=version.storage_container,
            blob_name=version.storage_blob_name,
            data=data,
            content_type=content_type,
        )
        resume = resume_service.complete_upload(
            db,
            tenant_id=auth.tenant_id,
            resume_id=session["resume_id"],  # type: ignore[arg-type]
            storage=storage,
        )
        db.commit()
    except ResumeServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc
    return {"resume_id": resume.id, "status": resume.status.value}


@router.post("/upload-sessions")
def create_upload_session(
    payload: UploadSessionRequest,
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    _: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter)),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    tenant_id = auth.tenant_id
    try:
        result = resume_service.create_upload_session(
            db,
            tenant_id=tenant_id,
            user_id=auth.user_id,
            filename=payload.filename,
            content_type=payload.content_type,
            byte_size=payload.byte_size,
            storage=_storage(),
        )
        db.commit()
        return result
    except ResumeServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Tenant context required.") from exc


@router.post("/complete-upload")
def complete_upload(
    payload: CompleteUploadRequest,
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    _: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter)),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    tenant_id = auth.tenant_id
    try:
        resume = resume_service.complete_upload(
            db, tenant_id=tenant_id, resume_id=payload.resume_id, storage=_storage()
        )
        db.commit()
        return {"resume_id": resume.id, "status": resume.status.value}
    except ResumeServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("")
def list_resumes(
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_roles(
        MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer
    ))],
) -> list[dict[str, object]]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    tenant_id = auth.tenant_id
    resumes = resume_service.list_resumes(db, tenant_id=tenant_id)
    items: list[dict[str, object]] = []
    for r in resumes:
        version = db.get(ResumeVersion, r.current_version_id) if r.current_version_id else None
        profile = version.extracted_profile if version is not None else None
        profile_dict = profile if isinstance(profile, dict) else {}
        job_titles = profile_dict.get("job_titles")
        titles = [str(t) for t in job_titles] if isinstance(job_titles, list) else []
        items.append(
            {
                "id": r.id,
                "status": r.status.value,
                "candidate_label": r.candidate_label,
                "full_name": profile_dict.get("full_name") or r.candidate_label,
                "email": profile_dict.get("email"),
                "phone": profile_dict.get("phone"),
                "location": profile_dict.get("location"),
                "headline": titles[0] if titles else None,
                "content_hash": r.content_hash,
                "original_filename": version.original_filename if version else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    return items


@router.get("/{resume_id}")
def get_resume(
    resume_id: uuid.UUID,
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_roles(
        MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer
    ))],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    tenant_id = auth.tenant_id
    try:
        resume = resume_service.get_resume(db, tenant_id=tenant_id, resume_id=resume_id)
    except ResumeServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {
        "id": resume.id,
        "status": resume.status.value,
        "candidate_label": resume.candidate_label,
        "current_version_id": resume.current_version_id,
    }


@router.delete("/{resume_id}")
def delete_resume(
    resume_id: uuid.UUID,
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    _: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter)),
    ],
) -> dict[str, str]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    tenant_id = auth.tenant_id
    try:
        resume_service.soft_delete_resume(db, tenant_id=tenant_id, resume_id=resume_id)
        db.commit()
    except ResumeServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {"status": "deletion_pending"}
