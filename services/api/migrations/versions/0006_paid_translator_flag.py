"""Admin switch for paid Translator fallback.

Revision ID: 0006_paid_translator_flag
Revises: 0005_localization_glossary
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_paid_translator_flag"
down_revision: str | None = "0005_localization_glossary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "localization_glossaries",
        sa.Column(
            "paid_translator_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("localization_glossaries", "paid_translator_enabled")
