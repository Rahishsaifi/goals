from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from recruitment_scoring.engine import validate_weights

from app.api.deps import DbSession, require_csrf, require_roles
from app.core.config import get_settings
from app.integrations.foundry_provider import FoundryProviderError
from app.integrations.model_provider import get_model_provider
from app.models.auth import MembershipRole
from app.models.domain import JobProfileVersion
from app.security.auth_context import AuthContext
from app.services import job_service
from app.services.job_service import JobServiceError

router = APIRouter(prefix="/job-profiles", tags=["job-profiles"])


class CreateJobProfileRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    source_text: str | None = None
    criteria: list[dict[str, object]] | None = None


class VersionRequest(BaseModel):
    criteria: list[dict[str, object]]
    source_text: str | None = None


class UpdateJobProfileRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    source_text: str | None = None
    criteria: list[dict[str, object]] | None = None


class ValidateWeightsRequest(BaseModel):
    criteria: list[dict[str, object]]


@router.post("")
def create_profile(
    payload: CreateJobProfileRequest,
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    _: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter)),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    provider = get_model_provider(get_settings().model_provider)
    try:
        profile = job_service.create_job_profile(
            db,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            title=payload.title,
            source_text=payload.source_text,
            criteria=payload.criteria,
            provider=provider,
        )
        db.commit()
    except FoundryProviderError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (JobServiceError, ValueError) as exc:
        db.rollback()
        message = exc.message if isinstance(exc, JobServiceError) else str(exc)
        status = exc.status_code if isinstance(exc, JobServiceError) else 400
        raise HTTPException(status_code=status, detail=message) from exc
    return {
        "id": profile.id,
        "title": profile.title,
        "current_version_id": profile.current_version_id,
        "model_provider": provider.name,
    }


@router.get("")
def list_profiles(
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(
            require_roles(
                MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer
            )
        ),
    ],
) -> list[dict[str, object]]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    profiles = job_service.list_profiles(db, tenant_id=auth.tenant_id)
    return [
        {"id": p.id, "title": p.title, "current_version_id": p.current_version_id}
        for p in profiles
    ]


@router.get("/{profile_id}")
def get_profile(
    profile_id: uuid.UUID,
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
        profile = job_service.get_profile(db, tenant_id=auth.tenant_id, profile_id=profile_id)
    except JobServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    version = db.get(JobProfileVersion, profile.current_version_id)
    return {
        "id": profile.id,
        "title": profile.title,
        "current_version_id": profile.current_version_id,
        "criteria": version.criteria if version else [],
        "source_text": version.source_text if version else None,
    }


@router.patch("/{profile_id}")
def update_profile(
    profile_id: uuid.UUID,
    payload: UpdateJobProfileRequest,
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    _: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter)),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    if payload.title is None and payload.source_text is None and payload.criteria is None:
        raise HTTPException(status_code=400, detail="No fields to update.")
    try:
        profile = job_service.update_job_profile(
            db,
            tenant_id=auth.tenant_id,
            profile_id=profile_id,
            title=payload.title,
            source_text=payload.source_text,
            criteria=payload.criteria,
        )
        db.commit()
    except (JobServiceError, ValueError) as exc:
        db.rollback()
        message = exc.message if isinstance(exc, JobServiceError) else str(exc)
        status = exc.status_code if isinstance(exc, JobServiceError) else 400
        raise HTTPException(status_code=status, detail=message) from exc
    version = db.get(JobProfileVersion, profile.current_version_id)
    return {
        "id": profile.id,
        "title": profile.title,
        "current_version_id": profile.current_version_id,
        "criteria": version.criteria if version else [],
        "source_text": version.source_text if version else None,
    }


@router.delete("/{profile_id}")
def delete_profile(
    profile_id: uuid.UUID,
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    _: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter)),
    ],
) -> dict[str, str]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    try:
        job_service.delete_job_profile(
            db, tenant_id=auth.tenant_id, profile_id=profile_id
        )
        db.commit()
    except JobServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {"status": "deleted"}


@router.post("/{profile_id}/versions")
def create_version(
    profile_id: uuid.UUID,
    payload: VersionRequest,
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
        version = job_service.add_version(
            db,
            tenant_id=auth.tenant_id,
            profile_id=profile_id,
            criteria=payload.criteria,
            source_text=payload.source_text,
        )
        db.commit()
    except (JobServiceError, ValueError) as exc:
        db.rollback()
        message = exc.message if isinstance(exc, JobServiceError) else str(exc)
        status = exc.status_code if isinstance(exc, JobServiceError) else 400
        raise HTTPException(status_code=status, detail=message) from exc
    return {"id": version.id, "version_number": version.version_number}


@router.post("/{profile_id}/validate-weights")
def validate_profile_weights(
    profile_id: uuid.UUID,
    payload: ValidateWeightsRequest,
    auth: Annotated[
        AuthContext,
        Depends(
            require_roles(
                MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer
            )
        ),
    ],
) -> dict[str, object]:
    del profile_id, auth
    try:
        validate_weights(payload.criteria)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"valid": True}
