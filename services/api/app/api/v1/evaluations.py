from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, model_validator
from sqlalchemy import select

from app.api.deps import DbSession, require_csrf, require_roles
from app.core.config import get_settings
from app.models.auth import MembershipRole
from app.models.domain import (
    EvaluationRun,
    EvaluationStatus,
    EvidenceItem,
    JobProfile,
    JobProfileVersion,
    Resume,
)
from app.security.auth_context import AuthContext
from app.services import evaluation_service
from app.services.evaluation_service import EvaluationServiceError

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


class CreateEvaluationRequest(BaseModel):
    job_profile_version_id: uuid.UUID | None = None
    job_profile_id: uuid.UUID | None = None
    resume_ids: list[uuid.UUID] | None = None

    @model_validator(mode="after")
    def require_one_target(self) -> CreateEvaluationRequest:
        if self.job_profile_version_id is None and self.job_profile_id is None:
            raise ValueError("Provide job_profile_id or job_profile_version_id.")
        if self.resume_ids is not None and len(self.resume_ids) == 0:
            raise ValueError("Select at least one ready resume.")
        return self


@router.get("")
def list_evaluations(
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
    return evaluation_service.list_evaluation_runs(db, tenant_id=auth.tenant_id)


@router.post("")
def create_evaluation(
    payload: CreateEvaluationRequest,
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    _: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter)),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    settings = get_settings()
    try:
        run = evaluation_service.create_evaluation_run(
            db,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            job_profile_version_id=payload.job_profile_version_id,
            job_profile_id=payload.job_profile_id,
            resume_ids=payload.resume_ids,
            provider_name=settings.model_provider,
        )
        db.commit()
    except EvaluationServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Processing is async via the worker + outbox so the UI can close and poll.
    return {
        "id": run.id,
        "status": run.status.value,
        "model_provider": run.model_provider,
        "job_title": (run.config_snapshot or {}).get("job_title"),
    }


@router.get("/{run_id}")
def get_evaluation(
    run_id: uuid.UUID,
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
    run = db.scalar(
        select(EvaluationRun).where(
            EvaluationRun.id == run_id, EvaluationRun.tenant_id == auth.tenant_id
        )
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    version = db.get(JobProfileVersion, run.job_profile_version_id)
    profile = db.get(JobProfile, version.job_profile_id) if version is not None else None
    return {
        "id": run.id,
        "status": run.status.value,
        "result_count": run.result_count,
        "failure_count": run.failure_count,
        "model_provider": run.model_provider,
        "job_profile_id": profile.id if profile else None,
        "job_title": profile.title if profile else "Unknown role",
        "job_profile_version_id": run.job_profile_version_id,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.get("/{run_id}/results")
def get_results(
    run_id: uuid.UUID,
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
    try:
        results = evaluation_service.list_results(db, tenant_id=auth.tenant_id, run_id=run_id)
    except EvaluationServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    run = db.scalar(
        select(EvaluationRun).where(
            EvaluationRun.id == run_id,
            EvaluationRun.tenant_id == auth.tenant_id,
        )
    )
    criteria_meta: dict[str, dict[str, object]] = {}
    if run is not None:
        raw_criteria = run.config_snapshot.get("criteria", [])
        if isinstance(raw_criteria, list):
            for item in raw_criteria:
                if isinstance(item, dict) and item.get("key") is not None:
                    criteria_meta[str(item["key"])] = item

    payload: list[dict[str, object]] = []
    for result in results:
        resume = db.get(Resume, result.resume_id)
        evidence_rows = list(
            db.scalars(
                select(EvidenceItem).where(EvidenceItem.candidate_result_id == result.id)
            )
        )
        evidence_by_key = {row.criterion_key: row for row in evidence_rows}
        criterion_scores = result.criterion_scores if isinstance(result.criterion_scores, list) else []
        breakdown: list[dict[str, object]] = []
        for item in criterion_scores:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", ""))
            meta = criteria_meta.get(key, {})
            evidence = evidence_by_key.get(key)
            breakdown.append(
                {
                    "key": key,
                    "display_name": str(meta.get("display_name") or key.replace("_", " ").title()),
                    "description": str(meta.get("description") or ""),
                    "weight": str(item.get("weight", "0")),
                    "score": str(item.get("score", "0")),
                    "contribution": str(item.get("contribution", "0")),
                    "status": str(item.get("status", "unknown")),
                    "mandatory": bool(item.get("mandatory", False)),
                    "passage": evidence.passage if evidence is not None else None,
                    "page_number": evidence.page_number if evidence is not None else None,
                }
            )
        payload.append(
            {
                "id": result.id,
                "resume_id": result.resume_id,
                "candidate_label": resume.candidate_label if resume else None,
                "overall_score": str(result.overall_score),
                "mandatory_status": result.mandatory_status.value,
                "review_required": result.review_required,
                "criterion_scores": result.criterion_scores,
                "score_breakdown": breakdown,
                "scoring_formula": "contribution = weight × criterion_score ÷ 100; overall = sum(contributions)",
            }
        )
    return payload


@router.post("/{run_id}/export")
def export_run(
    run_id: uuid.UUID,
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    _: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter)),
    ],
) -> Response:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    try:
        job = evaluation_service.export_results_csv(
            db, tenant_id=auth.tenant_id, run_id=run_id, user_id=auth.user_id
        )
        db.commit()
    except EvaluationServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    content = job.storage_blob_name or ""
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="evaluation-{run_id}.csv"'},
    )


@router.delete("/{run_id}")
def delete_run(
    run_id: uuid.UUID,
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
        evaluation_service.delete_evaluation_run(
            db, tenant_id=auth.tenant_id, run_id=run_id
        )
        db.commit()
    except EvaluationServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {"status": "deleted"}


@router.post("/{run_id}/cancel")
def cancel_run(
    run_id: uuid.UUID,
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    _: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin, MembershipRole.recruiter)),
    ],
) -> dict[str, str]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    run = db.scalar(
        select(EvaluationRun).where(
            EvaluationRun.id == run_id, EvaluationRun.tenant_id == auth.tenant_id
        )
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    if run.status.value in {"completed", "completed_with_warnings"}:
        raise HTTPException(status_code=400, detail="Completed runs cannot be cancelled.")
    run.status = EvaluationStatus.cancelled
    db.commit()
    return {"status": "cancelled"}
