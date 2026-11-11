from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.goals_localization import LocalizationJob, LocalizationJobStatus
from app.services.goals_localization import notifications
from app.services.goals_localization.glossary_store import JOB_EMAIL_EVENTS, JobEmailSettings


def _job(status: LocalizationJobStatus, *, production_ready: bool = False) -> LocalizationJob:
    started = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
    return LocalizationJob(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        tenant_id=uuid.uuid4(),
        target_language="nl",
        source_blob_name="s",
        template_blob_name="t",
        source_filename="goals.csv",
        template_filename="",
        status=status,
        production_ready=production_ready,
        total_records=5600,
        processed_records=5600,
        failed_records=14,
        stage_progress={"file_validation": {"started_at": started.isoformat()}},
        summary={
            "corrected_records": 15234,
            "unresolved_high_severity_issues": 2,
            "unresolved_terminology_issues": 13,
            "unresolved_untranslated_english": 36,
            "hard_gate": [
                {"name": "terminology", "passed": False},
                {"name": "blank cells", "passed": True},
            ],
        },
        created_at=started,
        completed_at=started + timedelta(minutes=25, seconds=4),
    )


def test_needs_review_summary_email() -> None:
    message = notifications.build_job_summary_email(
        _job(LocalizationJobStatus.needs_review), ["ops@example.com"]
    )

    assert message.to == ["ops@example.com"]
    assert message.subject == "Goals Translation needs review: goals.csv (Dutch)"
    assert "Rows processed: 5,600 of 5,600" in message.text
    assert "Total time: 25m 4s" in message.text
    assert "Fields improved by AI review: 15,234" in message.text
    assert "Final quality gate: Not passed: terminology" in message.text
    assert "only the affected rows" in message.text
    assert "/localization/11111111-1111-1111-1111-111111111111" in message.text
    assert "Needs review" in message.html


def test_completed_with_issues_and_ready_subjects() -> None:
    with_issues = _job(LocalizationJobStatus.completed)
    ready = _job(LocalizationJobStatus.completed, production_ready=True)

    assert (
        notifications.build_job_summary_email(with_issues, ["a@b.co"]).subject
        == "Goals Translation completed with issues: goals.csv (Dutch)"
    )
    message = notifications.build_job_summary_email(ready, ["a@b.co"])
    assert message.subject == "Goals Translation completed: goals.csv (Dutch)"
    assert "Your translation is ready" in message.text


def test_failed_job_email_shows_error() -> None:
    job = _job(LocalizationJobStatus.failed)
    job.error_message = "Translator quota exceeded"

    message = notifications.build_job_summary_email(job, ["ops@example.com"])

    assert message.subject == "Goals Translation failed: goals.csv (Dutch)"
    assert "Error: Translator quota exceeded" in message.text
    assert "quality gate" not in message.text


def test_started_email() -> None:
    job = _job(LocalizationJobStatus.uploaded)
    job.options = {"qa_mode": "foundry"}

    message = notifications.build_job_started_email(job, ["ops@example.com"])

    assert message.subject == "Goals Translation started: goals.csv (Dutch)"
    assert "Quality mode: Foundry AI review" in message.text
    assert "Rows: 5,600" in message.text


def _preferences(
    monkeypatch: pytest.MonkeyPatch,
    *,
    enabled: bool = True,
    recipients: list[str] | None = None,
    events: list[str] | None = None,
) -> list[str]:
    settings = JobEmailSettings(
        enabled=enabled,
        recipients=["ops@example.com"] if recipients is None else recipients,
        events=list(JOB_EMAIL_EVENTS) if events is None else events,
    )
    monkeypatch.setattr(notifications, "load_job_email_settings", lambda db, tenant_id: settings)
    monkeypatch.setattr(notifications, "email_configured", lambda: True)
    sent: list[str] = []
    monkeypatch.setattr(notifications, "send_email", lambda message: sent.append(message.subject))
    return sent


def test_notify_skips_without_email_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _preferences(monkeypatch)
    monkeypatch.delenv("AZURE_COMMUNICATION_CONNECTION_STRING", raising=False)
    monkeypatch.setattr(notifications, "email_configured", lambda: False)

    job = _job(LocalizationJobStatus.completed)
    assert notifications.notify_job_finished(None, job) is False  # type: ignore[arg-type]
    assert sent == []


def test_notify_respects_admin_switch_and_empty_recipients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _job(LocalizationJobStatus.completed)
    sent = _preferences(monkeypatch, enabled=False)
    assert not notifications.notify_job_started(None, job)  # type: ignore[arg-type]
    assert not notifications.notify_job_finished(None, job)  # type: ignore[arg-type]

    sent += _preferences(monkeypatch, recipients=[])
    assert not notifications.notify_job_finished(None, job)  # type: ignore[arg-type]
    assert sent == []


def test_notify_only_selected_events(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _preferences(monkeypatch, events=["needs_review", "failed"])

    completed = _job(LocalizationJobStatus.completed, production_ready=True)
    review = _job(LocalizationJobStatus.needs_review)
    assert not notifications.notify_job_started(None, completed)  # type: ignore[arg-type]
    assert not notifications.notify_job_finished(None, completed)  # type: ignore[arg-type]
    assert notifications.notify_job_finished(None, review)  # type: ignore[arg-type]
    assert sent == ["Goals Translation needs review: goals.csv (Dutch)"]


def test_notify_sends_and_survives_send_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _preferences(monkeypatch)

    finished = _job(LocalizationJobStatus.completed, production_ready=True)
    assert notifications.notify_job_started(None, finished)  # type: ignore[arg-type]
    assert notifications.notify_job_finished(None, finished)  # type: ignore[arg-type]
    assert sent == [
        "Goals Translation started: goals.csv (Dutch)",
        "Goals Translation completed: goals.csv (Dutch)",
    ]
    cancelled = _job(LocalizationJobStatus.cancelled)
    assert not notifications.notify_job_finished(None, cancelled)  # type: ignore[arg-type]

    def boom(message: object) -> str:
        raise RuntimeError("send failed")

    monkeypatch.setattr(notifications, "send_email", boom)
    failed = _job(LocalizationJobStatus.failed)
    assert notifications.notify_job_finished(None, failed) is False  # type: ignore[arg-type]
