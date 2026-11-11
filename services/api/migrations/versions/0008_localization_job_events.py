"""Runtime activity log for Goals localization jobs.

Revision ID: 0008_localization_job_events
Revises: 0007_semantic_prompt
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_localization_job_events"
down_revision: str | None = "0007_semantic_prompt"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'localization_jobs' "
            "AND column_name = 'events'"
        )
    ).scalar()
    if exists:
        return
    op.add_column(
        "localization_jobs",
        sa.Column(
            "events",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("localization_jobs", "events")
