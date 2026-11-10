from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from recruitment_scoring.engine import CriterionInput, score_candidate
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.integrations.model_provider import CriterionAssessment, ModelProvider
from app.models.domain import (
    CandidateResult,
    EvaluationRun,
    EvaluationStatus,
    EvidenceItem,
    EvidenceStatus,
    ExportJob,
    JobProfileVersion,
    OutboxEvent,
    ProcessingStatus,
    Resume,
    ResumeVersion,
    UsageEvent,
)
from app.services import usage_service


def _as_optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _resume_profile_payload(version: ResumeVersion | None) -> dict[str, object] | None:
    if version is None:
        return None
    raw = version.extracted_profile
    if isinstance(raw, dict) and raw:
        return dict(raw)
    # Older resumes may only have plain text; build a minimal reusable profile.
    text = (version.extracted_text or "").strip()
    if not text:
        return None
    return {
        "summary": text[:1200],
        "skills": [],
        "job_titles": [],
        "employers": [],
        "qualifications": [],
        "evidence_passages": [text[:400]],
    }


class EvaluationServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


_ACTIVE_RUN_STATUSES = {
    EvaluationStatus.queued,
    EvaluationStatus.retrieving,
    EvaluationStatus.evaluating,
}
# One Foundry call per resume (all criteria from stored profile).
_SECONDS_PER_RESUME = 8


def _estimate_run_seconds(snapshot: dict[str, object], *, selected_count: int) -> int:
    _ = snapshot
    candidates = max(selected_count, 1)
    return max(30, candidates * _SECONDS_PER_RESUME)


def list_evaluation_runs(
    db: Session, *, tenant_id: uuid.UUID, limit: int = 50
) -> list[dict[str, object]]:
    from app.models.domain import JobProfile

    runs = list(
        db.scalars(
            select(EvaluationRun)
            .where(EvaluationRun.tenant_id == tenant_id)
            .order_by(EvaluationRun.created_at.desc())
            .limit(limit)
        )
    )
    # Oldest active first = processing queue order.
    active_queue = sorted(
        [run for run in runs if run.status in _ACTIVE_RUN_STATUSES],
        key=lambda item: item.created_at or datetime.now(UTC),
    )
    queue_eta_seconds: dict[uuid.UUID, int] = {}
    cumulative = 0
    now = datetime.now(UTC)
    for run in active_queue:
        snapshot = run.config_snapshot if isinstance(run.config_snapshot, dict) else {}
        selected_raw = snapshot.get("resume_ids")
        selected_count = len(selected_raw) if isinstance(selected_raw, list) else 1
        own = _estimate_run_seconds(snapshot, selected_count=selected_count)
        # If a run has already been waiting, don't let ETA go into the past.
        started = run.created_at or now
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        elapsed = max(0, int((now - started).total_seconds()))
        remaining_own = max(30, own - (elapsed if run == active_queue[0] else 0))
        cumulative += remaining_own if run == active_queue[0] else own
        # For the head of queue, ETA is remaining_own; for later jobs, include prior work.
        if run == active_queue[0]:
            queue_eta_seconds[run.id] = remaining_own
            cumulative = remaining_own
        else:
            cumulative += own
            queue_eta_seconds[run.id] = cumulative

    items: list[dict[str, object]] = []
    for run in runs:
        version = db.get(JobProfileVersion, run.job_profile_version_id)
        profile = (
            db.get(JobProfile, version.job_profile_id) if version is not None else None
        )
        snapshot = run.config_snapshot if isinstance(run.config_snapshot, dict) else {}
        snapshot_title = snapshot.get("job_title")
        job_title = (
            profile.title
            if profile is not None
            else str(snapshot_title)
            if isinstance(snapshot_title, str) and snapshot_title
            else "Unknown role"
        )
        top = db.scalar(
            select(CandidateResult.overall_score)
            .where(
                CandidateResult.evaluation_run_id == run.id,
                CandidateResult.tenant_id == tenant_id,
            )
            .order_by(CandidateResult.overall_score.desc())
            .limit(1)
        )
        selected_raw = snapshot.get("resume_ids")
        selected_count = (
            len(selected_raw)
            if isinstance(selected_raw, list)
            else run.result_count
        )
        eta_seconds = queue_eta_seconds.get(run.id)
        eta_at = (
            (now + __import__("datetime").timedelta(seconds=eta_seconds)).isoformat()
            if eta_seconds is not None
            else None
        )
        items.append(
            {
                "id": run.id,
                "status": run.status.value,
                "result_count": run.result_count,
                "selected_count": selected_count,
                "failure_count": run.failure_count,
                "model_provider": run.model_provider,
                "job_profile_id": profile.id if profile else snapshot.get("job_profile_id"),
                "job_title": job_title,
                "job_profile_version_id": run.job_profile_version_id,
                "top_match_score": str(top) if top is not None else None,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "eta_seconds": eta_seconds,
                "eta_at": eta_at,
            }
        )
    return items


def create_evaluation_run(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    job_profile_version_id: uuid.UUID | None = None,
    job_profile_id: uuid.UUID | None = None,
    resume_ids: list[uuid.UUID] | None = None,
    provider_name: str,
) -> EvaluationRun:
    from app.models.domain import JobProfile

    if job_profile_version_id is None and job_profile_id is None:
        raise EvaluationServiceError(
            "invalid_request",
            "Provide job_profile_id or job_profile_version_id.",
            400,
        )

    version: JobProfileVersion | None = None
    if job_profile_version_id is not None:
        version = db.scalar(
            select(JobProfileVersion).where(
                JobProfileVersion.id == job_profile_version_id,
                JobProfileVersion.tenant_id == tenant_id,
            )
        )
        if version is None:
            raise EvaluationServiceError("not_found", "Job profile version not found.", 404)
    else:
        assert job_profile_id is not None
        profile = db.scalar(
            select(JobProfile).where(
                JobProfile.id == job_profile_id, JobProfile.tenant_id == tenant_id
            )
        )
        if profile is None or profile.current_version_id is None:
            raise EvaluationServiceError("not_found", "Job profile not found.", 404)
        version = db.get(JobProfileVersion, profile.current_version_id)
        if version is None or version.tenant_id != tenant_id:
            raise EvaluationServiceError("not_found", "Job profile version not found.", 404)

    selected_resume_ids: list[str] | None = None
    if resume_ids is not None:
        if len(resume_ids) == 0:
            raise EvaluationServiceError(
                "invalid_request",
                "Select at least one ready resume.",
                400,
            )
        ready = list(
            db.scalars(
                select(Resume).where(
                    Resume.tenant_id == tenant_id,
                    Resume.deleted_at.is_(None),
                    Resume.status == ProcessingStatus.ready,
                    Resume.id.in_(resume_ids),
                )
            )
        )
        found = {item.id for item in ready}
        missing = [str(item) for item in resume_ids if item not in found]
        if missing:
            raise EvaluationServiceError(
                "invalid_request",
                "One or more selected resumes are missing or not ready.",
                400,
            )
        selected_resume_ids = [str(item.id) for item in ready]

    from app.models.domain import JobProfile

    profile_for_title = db.get(JobProfile, version.job_profile_id)
    run = EvaluationRun(
        tenant_id=tenant_id,
        job_profile_version_id=version.id,
        created_by_user_id=user_id,
        status=EvaluationStatus.queued,
        config_snapshot={
            "criteria": version.criteria,
            "scoring_algorithm_version": version.scoring_algorithm_version,
            "job_profile_version_id": str(version.id),
            "job_profile_id": str(version.job_profile_id),
            "job_title": profile_for_title.title if profile_for_title is not None else "Unknown role",
            "resume_ids": selected_resume_ids,
        },
        model_provider=provider_name,
    )
    db.add(run)
    db.flush()
    db.add(
        OutboxEvent(
            tenant_id=tenant_id,
            event_type="evaluation.run",
            aggregate_type="evaluation_run",
            aggregate_id=run.id,
            payload={"evaluation_run_id": str(run.id), "tenant_id": str(tenant_id)},
        )
    )
    db.flush()
    return run


def process_evaluation_run(
    db: Session, *, run_id: uuid.UUID, provider: ModelProvider
) -> EvaluationRun:
    run = db.get(EvaluationRun, run_id)
    if run is None:
        raise EvaluationServiceError("not_found", "Evaluation run not found.", 404)
    if run.status in {EvaluationStatus.completed, EvaluationStatus.cancelled}:
        return run
    run.status = EvaluationStatus.retrieving
    db.flush()
    selected_raw = run.config_snapshot.get("resume_ids")
    selected_ids: list[uuid.UUID] | None = None
    if isinstance(selected_raw, list) and selected_raw:
        parsed: list[uuid.UUID] = []
        for item in selected_raw:
            try:
                parsed.append(uuid.UUID(str(item)))
            except ValueError:
                continue
        selected_ids = parsed or None
    query = select(Resume).where(
        Resume.tenant_id == run.tenant_id,
        Resume.deleted_at.is_(None),
        Resume.status == ProcessingStatus.ready,
    )
    if selected_ids is not None:
        query = query.where(Resume.id.in_(selected_ids))
    resumes = list(db.scalars(query))
    run.status = EvaluationStatus.evaluating
    db.flush()
    raw_criteria = run.config_snapshot.get("criteria", [])
    criteria: list[dict[str, object]] = (
        [dict(item) for item in raw_criteria] if isinstance(raw_criteria, list) else []
    )
    failures = 0
    for resume in resumes:
        version = db.get(ResumeVersion, resume.current_version_id)
        profile = _resume_profile_payload(version)
        if version is None or profile is None:
            failures += 1
            continue
        batch = provider.assess_criteria_from_profile(criteria=criteria, profile=profile)
        usage_service.record_usage(
            db,
            tenant_id=run.tenant_id,
            operation_type="evidence_assessment",
            provider=provider.name,
            usage=batch.usage,
            idempotency_key=f"eval-{run.id}-{resume.id}-profile-batch",
            evaluation_run_id=run.id,
            resume_id=resume.id,
        )
        by_key = {item.criterion_key: item for item in batch.value}
        criterion_inputs: list[CriterionInput] = []
        assessments: list[dict[str, object]] = []
        for criterion in criteria:
            key = str(criterion.get("key", "unknown"))
            value = by_key.get(
                key,
                CriterionAssessment(
                    criterion_key=key,
                    score=0.0,
                    status="unknown",
                    passage=None,
                    page_number=None,
                ),
            )
            criterion_inputs.append(
                CriterionInput(
                    key=value.criterion_key,
                    weight=Decimal(str(criterion.get("weight", 0))),
                    mandatory=bool(criterion.get("mandatory", False)),
                    score=Decimal(str(value.score)),
                    status=value.status,
                )
            )
            assessments.append(value.model_dump())
        scored = score_candidate(criterion_inputs)
        result = CandidateResult(
            tenant_id=run.tenant_id,
            evaluation_run_id=run.id,
            resume_id=resume.id,
            resume_version_id=version.id,
            overall_score=scored.overall_score,
            mandatory_status=EvidenceStatus(scored.mandatory_status),
            review_required=scored.review_required,
            criterion_scores=scored.contributions,
        )
        db.add(result)
        db.flush()
        for item in assessments:
            db.add(
                EvidenceItem(
                    tenant_id=run.tenant_id,
                    candidate_result_id=result.id,
                    criterion_key=str(item["criterion_key"]),
                    status=EvidenceStatus(str(item["status"])),
                    passage=str(item["passage"]) if item.get("passage") is not None else None,
                    page_number=_as_optional_int(item.get("page_number")),
                )
            )
    run.result_count = len(resumes) - failures
    run.failure_count = failures
    run.status = (
        EvaluationStatus.completed_with_warnings if failures else EvaluationStatus.completed
    )
    run.completed_at = datetime.now(UTC)
    db.flush()
    return run


def delete_evaluation_run(db: Session, *, tenant_id: uuid.UUID, run_id: uuid.UUID) -> None:
    run = db.scalar(
        select(EvaluationRun).where(
            EvaluationRun.id == run_id,
            EvaluationRun.tenant_id == tenant_id,
        )
    )
    if run is None:
        raise EvaluationServiceError("not_found", "Evaluation run not found.", 404)
    db.execute(
        delete(ExportJob).where(
            ExportJob.evaluation_run_id == run.id,
            ExportJob.tenant_id == tenant_id,
        )
    )
    db.execute(
        delete(OutboxEvent).where(
            OutboxEvent.tenant_id == tenant_id,
            OutboxEvent.aggregate_id == run.id,
            OutboxEvent.event_type == "evaluation.run",
            OutboxEvent.processed_at.is_(None),
        )
    )
    db.execute(
        update(UsageEvent)
        .where(
            UsageEvent.evaluation_run_id == run.id,
            UsageEvent.tenant_id == tenant_id,
        )
        .values(evaluation_run_id=None)
    )
    db.delete(run)
    db.flush()


def list_results(db: Session, *, tenant_id: uuid.UUID, run_id: uuid.UUID) -> list[CandidateResult]:
    run = db.scalar(
        select(EvaluationRun).where(
            EvaluationRun.id == run_id,
            EvaluationRun.tenant_id == tenant_id,
        )
    )
    if run is None:
        raise EvaluationServiceError("not_found", "Evaluation run not found.", 404)
    return list(
        db.scalars(
            select(CandidateResult)
            .where(
                CandidateResult.evaluation_run_id == run_id,
                CandidateResult.tenant_id == tenant_id,
            )
            .order_by(CandidateResult.overall_score.desc(), CandidateResult.resume_id.asc())
        )
    )


def export_results_csv(
    db: Session, *, tenant_id: uuid.UUID, run_id: uuid.UUID, user_id: uuid.UUID
) -> ExportJob:
    results = list_results(db, tenant_id=tenant_id, run_id=run_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "candidate_reference_id",
            "overall_fit_score",
            "mandatory_requirement_status",
            "review_required",
            "evaluation_run_id",
        ]
    )
    for result in results:
        # Neutralize spreadsheet formula injection.
        resume_ref = str(result.resume_id)
        if resume_ref[:1] in {"=", "+", "-", "@"}:
            resume_ref = "'" + resume_ref
        writer.writerow(
            [
                resume_ref,
                str(result.overall_score),
                result.mandatory_status.value,
                result.review_required,
                str(run_id),
            ]
        )
    job = ExportJob(
        tenant_id=tenant_id,
        evaluation_run_id=run_id,
        status="completed",
        storage_blob_name=None,
        created_by_user_id=user_id,
        expires_at=datetime.now(UTC),
    )
    db.add(job)
    db.flush()
    job.storage_blob_name = buffer.getvalue()
    db.flush()
    return job
