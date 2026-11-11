"""Admin settings for localization job emails: on/off, recipients and events.

Revision ID: 0009_job_emails_flag
Revises: 0008_localization_job_events
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_job_emails_flag"
down_revision: str | None = "0008_localization_job_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS: list[tuple[str, sa.types.TypeEngine[object], sa.TextClause]] = [
    ("job_emails_enabled", sa.Boolean(), sa.text("true")),
    ("job_email_recipients", postgresql.JSONB(astext_type=sa.Text()), sa.text("'[]'::jsonb")),
    (
        "job_email_events",
        postgresql.JSONB(astext_type=sa.Text()),
        sa.text('\'["started", "completed", "needs_review", "failed"]\'::jsonb'),
    ),
]


def upgrade() -> None:
    bind = op.get_bind()
    for name, column_type, default in _COLUMNS:
        exists = bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'localization_glossaries' AND column_name = :name"
            ),
            {"name": name},
        ).scalar()
        if exists:
            continue
        op.add_column(
            "localization_glossaries",
            sa.Column(name, column_type, nullable=False, server_default=default),
        )


def downgrade() -> None:
    for name, _, _ in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE localization_glossaries DROP COLUMN IF EXISTS {name}")
