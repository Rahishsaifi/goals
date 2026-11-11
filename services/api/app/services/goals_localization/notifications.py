from __future__ import annotations

import html
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.goals_localization.language_config import resolve_language
from app.integrations.email import EmailMessage, email_configured, send_email
from app.models.goals_localization import LocalizationJob, LocalizationJobStatus
from app.services.goals_localization.glossary_store import load_job_email_settings

logger = logging.getLogger(__name__)

PRODUCT_NAME = "TalentMatch AI"
FEATURE_NAME = "Goals Translation"
Rows = list[tuple[str, str]]


@dataclass(frozen=True)
class _Status:
    label: str
    subject_verb: str
    color: str
    background: str


_STARTED = _Status("Started", "started", "#4338ca", "#eef2ff")
_COMPLETED = _Status("Completed", "completed", "#047857", "#ecfdf5")
_WITH_ISSUES = _Status("Completed with issues", "completed with issues", "#b45309", "#fffbeb")
_NEEDS_REVIEW = _Status("Needs review", "needs review", "#b45309", "#fffbeb")
_FAILED = _Status("Failed", "failed", "#b91c1c", "#fef2f2")


def finished_event(job: LocalizationJob) -> str | None:
    if job.status == LocalizationJobStatus.failed:
        return "failed"
    if job.status == LocalizationJobStatus.needs_review:
        return "needs_review"
    if job.status == LocalizationJobStatus.completed:
        return "completed"
    return None


def _finished_status(job: LocalizationJob) -> _Status:
    if job.status == LocalizationJobStatus.failed:
        return _FAILED
    if job.production_ready:
        return _COMPLETED
    if job.status == LocalizationJobStatus.needs_review:
        return _NEEDS_REVIEW
    return _WITH_ISSUES


def _duration(job: LocalizationJob) -> str:
    starts: list[datetime] = []
    for stage in (job.stage_progress or {}).values():
        if isinstance(stage, dict) and stage.get("started_at"):
            try:
                starts.append(datetime.fromisoformat(str(stage["started_at"])))
            except ValueError:
                continue
    start = min(starts) if starts else job.created_at
    if job.completed_at is None or start is None:
        return "—"
    seconds = max(0, int((job.completed_at - start).total_seconds()))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _timestamp(value: datetime | None) -> str:
    return (value or datetime.now(UTC)).astimezone(UTC).strftime("%d %b %Y, %H:%M UTC")


def _language_name(code: str) -> str:
    try:
        return resolve_language(code).name
    except Exception:
        return code


def _count(summary: dict[str, object], key: str) -> int:
    try:
        return int(str(summary.get(key) or 0))
    except ValueError:
        return 0


def _job_link(job: LocalizationJob) -> str:
    return f"{get_settings().web_base_url.rstrip('/')}/localization/{job.id}"


def _subject(status: _Status, job: LocalizationJob, language: str) -> str:
    return f"{FEATURE_NAME} {status.subject_verb}: {job.source_filename} ({language})"


def build_job_summary_email(job: LocalizationJob, recipients: list[str]) -> EmailMessage:
    summary = job.summary or {}
    status = _finished_status(job)
    language = _language_name(job.target_language)
    file = job.source_filename

    details: Rows = [
        ("File", file),
        ("Language", language),
        ("Rows processed", f"{job.processed_records:,} of {job.total_records:,}"),
        ("Total time", _duration(job)),
        ("Finished", _timestamp(job.completed_at)),
    ]
    quality: Rows = []
    if status is _FAILED:
        heading = "Your translation job stopped"
        intro = (
            f"The {language} translation of {file} stopped before it finished, "
            "so no output file was produced. The error is below."
        )
        quality.append(("Error", (job.error_message or "Unknown error")[:500]))
    else:
        gate = summary.get("hard_gate")
        failed_checks = [
            str(check.get("name"))
            for check in (gate if isinstance(gate, list) else [])
            if isinstance(check, dict) and not check.get("passed")
        ]
        high = _count(summary, "unresolved_high_severity_issues")
        terms = _count(summary, "unresolved_terminology_issues")
        english = _count(summary, "unresolved_untranslated_english")
        quality = [
            ("Fields improved by AI review", f"{_count(summary, 'corrected_records'):,}"),
            ("High-severity issues", f"{high:,}"),
            ("Terminology issues", f"{terms:,}"),
            ("Untranslated English", f"{english:,}"),
            (
                "Final quality gate",
                "Passed" if job.production_ready else "Not passed: " + ", ".join(failed_checks),
            ),
        ]
        if status is _COMPLETED:
            heading = "Your translation is ready"
            intro = (
                f"The {language} translation of {file} passed every quality check. "
                "The production-ready Excel file is ready to download."
            )
        else:
            heading = "Your translation needs a review"
            intro = (
                f"The {language} translation of {file} finished, but it did not pass the "
                "final quality gate. Please review the open issues before using the file. "
                + (
                    "The job page has a file with only the affected rows."
                    if status is _NEEDS_REVIEW
                    else "The details are on the job page."
                )
            )

    sections = [("Job details", details), ("Quality summary", quality)]
    return EmailMessage(
        to=recipients,
        subject=_subject(status, job, language),
        text=_text(heading, intro, sections, _job_link(job)),
        html=_html(status, heading, intro, sections, _job_link(job)),
    )


def build_job_started_email(job: LocalizationJob, recipients: list[str]) -> EmailMessage:
    language = _language_name(job.target_language)
    mode = (
        "Foundry AI review" if str((job.options or {}).get("qa_mode")) == "foundry" else "Classic"
    )
    details: Rows = [
        ("File", job.source_filename),
        ("Language", language),
        ("Quality mode", mode),
    ]
    if job.total_records:
        details.append(("Rows", f"{job.total_records:,}"))
    details.append(("Started", _timestamp(None)))
    heading = "Your translation has started"
    intro = (
        f"We started translating {job.source_filename} into {language}. "
        "We will email you again when it finishes."
    )
    sections = [("Job details", details)]
    return EmailMessage(
        to=recipients,
        subject=_subject(_STARTED, job, language),
        text=_text(heading, intro, sections, _job_link(job)),
        html=_html(_STARTED, heading, intro, sections, _job_link(job)),
    )


_FOOTER = (
    f"You received this email because you are on the {FEATURE_NAME} notification list. "
    "An admin can change the recipients or turn these emails off in Settings."
)


def _text(heading: str, intro: str, sections: list[tuple[str, Rows]], link: str) -> str:
    lines = [heading, "", intro]
    for title, rows in sections:
        lines += ["", title.upper(), *[f"  {key}: {value}" for key, value in rows]]
    lines += ["", f"View job: {link}", "", "—", f"{PRODUCT_NAME} · {FEATURE_NAME}", _FOOTER]
    return "\n".join(lines)


def _html(
    status: _Status, heading: str, intro: str, sections: list[tuple[str, Rows]], link: str
) -> str:
    def row(key: str, value: str) -> str:
        warn = key.endswith("issues") or key == "Untranslated English"
        highlight = (warn and value not in {"0", ""}) or value.startswith("Not passed")
        color = status.color if highlight and status is not _COMPLETED else "#0f172a"
        if value == "Passed":
            color = "#047857"
        return (
            "<tr>"
            '<td style="padding:8px 16px 8px 0;color:#64748b;font-size:14px;'
            f'border-bottom:1px solid #f1f5f9;white-space:nowrap">{html.escape(key)}</td>'
            f'<td style="padding:8px 0;color:{color};font-size:14px;font-weight:600;'
            f'border-bottom:1px solid #f1f5f9">{html.escape(value)}</td>'
            "</tr>"
        )

    blocks = "".join(
        f'<h3 style="margin:24px 0 4px;color:#64748b;font-size:12px;letter-spacing:.06em;'
        f'text-transform:uppercase">{html.escape(title)}</h3>'
        '<table role="presentation" style="border-collapse:collapse;width:100%">'
        + "".join(row(key, value) for key, value in rows)
        + "</table>"
        for title, rows in sections
        if rows
    )
    safe_link = html.escape(link)
    return (
        '<div style="background:#f8fafc;padding:24px 12px;'
        "font-family:'Segoe UI',Helvetica,Arial,sans-serif\">"
        '<div style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;'
        'border-radius:12px;overflow:hidden">'
        '<div style="padding:16px 28px;background:#0f172a;color:#ffffff;font-size:14px;'
        f'font-weight:600">{PRODUCT_NAME} <span style="color:#94a3b8;font-weight:400">'
        f"· {FEATURE_NAME}</span></div>"
        '<div style="padding:28px">'
        f'<span style="display:inline-block;padding:3px 10px;border-radius:999px;'
        f"background:{status.background};color:{status.color};font-size:12px;"
        f'font-weight:700">{html.escape(status.label)}</span>'
        f'<h2 style="margin:12px 0 8px;color:#0f172a;font-size:20px">{html.escape(heading)}</h2>'
        f'<p style="margin:0;color:#334155;font-size:14px;line-height:22px">'
        f"{html.escape(intro)}</p>"
        f"{blocks}"
        f'<p style="margin:28px 0 0"><a href="{safe_link}" style="display:inline-block;'
        "background:#4f46e5;color:#ffffff;padding:10px 20px;border-radius:8px;"
        'text-decoration:none;font-size:14px;font-weight:600">View job</a></p>'
        f'<p style="margin:12px 0 0;color:#94a3b8;font-size:12px">Or open: '
        f'<a href="{safe_link}" style="color:#6366f1">{safe_link}</a></p>'
        "</div></div>"
        '<p style="max-width:560px;margin:16px auto 0;color:#94a3b8;font-size:12px;'
        f'line-height:18px;text-align:center">{html.escape(_FOOTER)}</p>'
        "</div>"
    )


def _send(
    db: Session,
    job: LocalizationJob,
    kind: str,
    build: Callable[[LocalizationJob, list[str]], EmailMessage],
) -> bool:
    """A send failure is logged and never changes the job."""
    preferences = load_job_email_settings(db, job.tenant_id)
    if not preferences.enabled or kind not in preferences.events or not preferences.recipients:
        logger.info("job_email_skipped kind=%s job_id=%s reason=settings", kind, job.id)
        return False
    recipients = preferences.recipients
    if not email_configured():
        logger.warning("job_email_skipped kind=%s job_id=%s reason=not_configured", kind, job.id)
        return False
    try:
        operation_id = send_email(build(job, recipients))
    except Exception:
        logger.exception("job_email_failed kind=%s job_id=%s", kind, job.id)
        return False
    logger.info("job_email_sent kind=%s job_id=%s operation_id=%s", kind, job.id, operation_id)
    return True


def notify_job_started(db: Session, job: LocalizationJob) -> bool:
    return _send(db, job, "started", build_job_started_email)


def notify_job_finished(db: Session, job: LocalizationJob) -> bool:
    event = finished_event(job)
    if event is None:
        return False
    return _send(db, job, event, build_job_summary_email)
