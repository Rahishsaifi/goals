from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings


class EmailNotConfiguredError(RuntimeError):
    pass


@dataclass(frozen=True)
class EmailMessage:
    to: list[str]
    subject: str
    text: str
    html: str


def email_configured() -> bool:
    settings = get_settings()
    return bool(settings.azure_communication_connection_string and settings.email_sender_address)


def send_email(message: EmailMessage, *, timeout_seconds: int = 15) -> str:
    """Send through Azure Communication Services Email and return the operation id.

    ACS often returns status ``Running`` while delivery is still in flight.
    That means the send was accepted — do not treat it as failure, and do not
    block the localization worker on a long poll.
    """
    settings = get_settings()
    if not settings.azure_communication_connection_string or not settings.email_sender_address:
        raise EmailNotConfiguredError("Azure Communication Services Email is not configured.")
    from azure.communication.email import EmailClient

    client = EmailClient.from_connection_string(settings.azure_communication_connection_string)
    poller = client.begin_send(
        {
            "senderAddress": settings.email_sender_address,
            "recipients": {"to": [{"address": address} for address in message.to]},
            "content": {
                "subject": message.subject,
                "plainText": message.text,
                "html": message.html,
            },
        }
    )
    result: dict[str, object]
    try:
        raw = poller.result(timeout=timeout_seconds)
        result = dict(raw) if raw else {}
    except Exception as exc:
        # Timed out waiting for final delivery — still accepted if we have an id.
        operation_id = str(getattr(poller, "id", "") or "")
        if operation_id:
            return operation_id
        raise RuntimeError(f"Email send did not complete: {exc}") from exc

    status = str(result.get("status", "")).lower()
    operation_id = str(result.get("id", "") or getattr(poller, "id", "") or "")
    if status in {"succeeded", "running", "notstarted"} and operation_id:
        return operation_id
    if status == "succeeded":
        return operation_id
    raise RuntimeError(f"Email send ended with status {status or 'unknown'}.")
