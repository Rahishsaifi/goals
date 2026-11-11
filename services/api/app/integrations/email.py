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


def send_email(message: EmailMessage, *, timeout_seconds: int = 60) -> str:
    """Send through Azure Communication Services Email and return the operation id."""
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
    result = poller.result(timeout=timeout_seconds)
    status = str(result.get("status", ""))
    if status.lower() != "succeeded":
        raise RuntimeError(f"Email send ended with status {status or 'unknown'}.")
    return str(result.get("id", ""))
