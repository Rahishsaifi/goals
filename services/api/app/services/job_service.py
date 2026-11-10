from __future__ import annotations

import uuid

from recruitment_scoring.engine import validate_weights
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.model_provider import ModelProvider
from app.models.domain import JobProfile, JobProfileVersion
from app.services import usage_service


class JobServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


DEFAULT_CRITERIA: list[dict[str, object]] = [
    {
        "key": "technical_skills",
        "display_name": "Technical skills",
        "weight": 30,
        "mandatory": True,
        "severity": "mandatory",
        "description": "Core technical skills",
    },
    {
        "key": "relevant_experience",
        "display_name": "Relevant experience",
        "weight": 20,
        "mandatory": False,
        "severity": "preferred",
        "description": "Relevant experience",
    },
    {
        "key": "project_domain",
        "display_name": "Project/domain experience",
        "weight": 15,
        "mandatory": False,
        "severity": "preferred",
        "description": "Domain experience",
    },
    {
        "key": "qualifications",
        "display_name": "Qualifications",
        "weight": 10,
        "mandatory": False,
        "severity": "informational",
        "description": "Qualifications",
    },
    {
        "key": "responsibilities",
        "display_name": "Role responsibilities",
        "weight": 15,
        "mandatory": False,
        "severity": "preferred",
        "description": "Responsibilities",
    },
    {
        "key": "preferred_skills",
        "display_name": "Preferred skills",
        "weight": 10,
        "mandatory": False,
        "severity": "preferred",
        "description": "Preferred skills",
    },
]


def create_job_profile(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    title: str,
    source_text: str | None,
    criteria: list[dict[str, object]] | None,
    provider: ModelProvider,
) -> JobProfile:
    resolved = list(criteria) if criteria else list(DEFAULT_CRITERIA)
    if source_text and criteria is None:
        extracted = provider.extract_jd_requirements(source_text)
        resolved = extracted.value
        usage_service.record_usage(
            db,
            tenant_id=tenant_id,
            operation_type="jd_extraction",
            provider=provider.name,
            usage=extracted.usage,
            idempotency_key=f"jd-extract-{tenant_id}-{uuid.uuid4()}",
        )
    validate_weights(resolved)
    profile = JobProfile(tenant_id=tenant_id, title=title, created_by_user_id=user_id)
    db.add(profile)
    db.flush()
    version = JobProfileVersion(
        job_profile_id=profile.id,
        tenant_id=tenant_id,
        version_number=1,
        source_text=source_text,
        criteria=resolved,
        scoring_algorithm_version="1",
    )
    db.add(version)
    db.flush()
    profile.current_version_id = version.id
    db.flush()
    return profile


def add_version(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    profile_id: uuid.UUID,
    criteria: list[dict[str, object]],
    source_text: str | None = None,
) -> JobProfileVersion:
    validate_weights(criteria)
    profile = db.scalar(
        select(JobProfile).where(JobProfile.id == profile_id, JobProfile.tenant_id == tenant_id)
    )
    if profile is None:
        raise JobServiceError("not_found", "Job profile not found.", status_code=404)
    current = db.get(JobProfileVersion, profile.current_version_id)
    next_version = 1 if current is None else current.version_number + 1
    version = JobProfileVersion(
        job_profile_id=profile.id,
        tenant_id=tenant_id,
        version_number=next_version,
        source_text=(
            source_text if source_text is not None else (current.source_text if current else None)
        ),
        criteria=criteria,
        scoring_algorithm_version="1",
    )
    db.add(version)
    db.flush()
    profile.current_version_id = version.id
    db.flush()
    return version


def list_profiles(db: Session, *, tenant_id: uuid.UUID) -> list[JobProfile]:
    return list(
        db.scalars(
            select(JobProfile)
            .where(JobProfile.tenant_id == tenant_id)
            .order_by(JobProfile.created_at.desc())
        )
    )


def get_profile(db: Session, *, tenant_id: uuid.UUID, profile_id: uuid.UUID) -> JobProfile:
    profile = db.scalar(
        select(JobProfile).where(JobProfile.id == profile_id, JobProfile.tenant_id == tenant_id)
    )
    if profile is None:
        raise JobServiceError("not_found", "Job profile not found.", status_code=404)
    return profile


def update_job_profile(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    profile_id: uuid.UUID,
    title: str | None = None,
    source_text: str | None = None,
    criteria: list[dict[str, object]] | None = None,
) -> JobProfile:
    profile = get_profile(db, tenant_id=tenant_id, profile_id=profile_id)
    if title is not None:
        cleaned = title.strip()
        if not cleaned:
            raise JobServiceError("invalid_title", "Title is required.")
        profile.title = cleaned

    current = db.get(JobProfileVersion, profile.current_version_id)
    if current is None:
        raise JobServiceError("not_found", "Job profile version not found.", status_code=404)

    next_criteria = list(criteria) if criteria is not None else list(current.criteria)
    text_changed = source_text is not None and source_text != current.source_text
    criteria_changed = criteria is not None and next_criteria != current.criteria
    if text_changed or criteria_changed:
        add_version(
            db,
            tenant_id=tenant_id,
            profile_id=profile.id,
            criteria=next_criteria,
            source_text=source_text if source_text is not None else current.source_text,
        )
    db.flush()
    return profile


def delete_job_profile(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    profile_id: uuid.UUID,
) -> None:
    profile = get_profile(db, tenant_id=tenant_id, profile_id=profile_id)
    versions = list(
        db.scalars(
            select(JobProfileVersion).where(
                JobProfileVersion.job_profile_id == profile.id,
                JobProfileVersion.tenant_id == tenant_id,
            )
        )
    )
    profile.current_version_id = None
    db.flush()
    for version in versions:
        db.delete(version)
    db.delete(profile)
    db.flush()
