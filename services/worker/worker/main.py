from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "api"))

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.integrations.foundry_provider import FoundryProviderError
from app.integrations.model_provider import get_model_provider
from app.integrations.storage import BlobStorage
from app.models.domain import OutboxEvent
from app.models.goals_localization import LocalizationJob
from app.services import evaluation_service, processing_service
from app.services.goals_localization.notifications import (
    notify_job_finished,
    notify_job_started,
)
from app.services.goals_localization.pipeline import process_localization_job


class WorkerSettings(BaseSettings):
    database_url: str = "postgresql+psycopg://recruitment:recruitment@localhost:5432/recruitment"
    model_provider: str = "mock"
    poll_seconds: float = 1.0
    once: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def _log_email(job: LocalizationJob, kind: str, sent: bool) -> None:
    print(
        json.dumps(
            {
                "component": "worker",
                "status": "job_email_sent" if sent else "job_email_skipped",
                "kind": kind,
                "job_id": str(job.id),
            }
        ),
        flush=True,
    )


def run_once(session_factory: sessionmaker[Session], settings: WorkerSettings) -> int:
    storage = BlobStorage()
    provider = get_model_provider(settings.model_provider)
    processed = 0
    db = session_factory()
    try:
        events = processing_service.claim_outbox_events(db, limit=1)
        db.commit()
    except Exception:
        db.rollback()
        db.close()
        raise

    for event in events:
        event_db = session_factory()
        finished_job: LocalizationJob | None = None
        try:
            locked = event_db.get(OutboxEvent, event.id)
            if locked is None or locked.processed_at is not None:
                continue
            print(
                json.dumps(
                    {
                        "component": "worker",
                        "status": "processing",
                        "event_type": locked.event_type,
                        "event_id": str(locked.id),
                    }
                ),
                flush=True,
            )
            if locked.event_type == "resume.process":
                version_id = uuid.UUID(str(locked.payload["version_id"]))
                processing_service.process_resume_version(
                    event_db, version_id=version_id, storage=storage, provider=provider
                )
            elif locked.event_type == "evaluation.run":
                run_id = uuid.UUID(str(locked.payload["evaluation_run_id"]))
                evaluation_service.process_evaluation_run(
                    event_db, run_id=run_id, provider=provider
                )
            elif locked.event_type == "goals.localization.run":
                from app.models.goals_localization import LocalizationJobStatus

                job_id = uuid.UUID(str(locked.payload["job_id"]))
                job = event_db.get(LocalizationJob, job_id)
                if job is not None and job.status == LocalizationJobStatus.cancelled:
                    print(
                        json.dumps(
                            {
                                "component": "worker",
                                "status": "skipped_cancelled",
                                "event_id": str(locked.id),
                                "job_id": str(job_id),
                            }
                        ),
                        flush=True,
                    )
                else:
                    if job is not None and job.status == LocalizationJobStatus.uploaded:
                        _log_email(job, "started", notify_job_started(event_db, job))
                    finished_job = process_localization_job(
                        event_db, job_id=job_id, storage=storage
                    )
            processing_service.mark_processed(event_db, locked)
            event_db.commit()
            processed += 1
            if finished_job is not None:
                _log_email(finished_job, "finished", notify_job_finished(event_db, finished_job))
            print(
                json.dumps(
                    {
                        "component": "worker",
                        "status": "processed",
                        "event_id": str(locked.id),
                    }
                ),
                flush=True,
            )
        except FoundryProviderError as exc:
            event_db.rollback()
            processing_service.release_outbox_event(event_db, event.id)
            print(
                json.dumps(
                    {
                        "component": "worker",
                        "status": "retry",
                        "event_id": str(event.id),
                        "error": str(exc)[:300],
                    }
                ),
                flush=True,
            )
            # Back off so rate-limited Foundry calls can recover.
            time.sleep(5)
        except Exception as exc:
            event_db.rollback()
            processing_service.release_outbox_event(event_db, event.id)
            print(
                json.dumps(
                    {
                        "component": "worker",
                        "status": "error",
                        "event_id": str(event.id),
                        "error": str(exc)[:300],
                    }
                ),
                flush=True,
            )
        finally:
            event_db.close()
    db.close()
    return processed


def main() -> int:
    settings = WorkerSettings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    if settings.once:
        count = run_once(session_factory, settings)
        print(json.dumps({"component": "worker", "processed": count, "mode": "once"}))
        return 0
    print(
        json.dumps(
            {
                "component": "worker",
                "status": "listening",
                "provider": settings.model_provider,
            }
        ),
        flush=True,
    )
    while True:
        try:
            run_once(session_factory, settings)
        except Exception as exc:
            print(
                json.dumps(
                    {"component": "worker", "status": "loop_error", "error": str(exc)[:300]}
                ),
                flush=True,
            )
            time.sleep(max(settings.poll_seconds, 5.0))
            continue
        time.sleep(settings.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
