"""Tenant override for the Foundry semantic revision prompt.

Revision ID: 0007_semantic_prompt
Revises: 0006_paid_translator_flag
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_semantic_prompt"
down_revision: str | None = "0006_paid_translator_flag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'localization_glossaries' "
            "AND column_name = 'semantic_prompt'"
        )
    ).scalar()
    if exists:
        return
    op.add_column(
        "localization_glossaries",
        sa.Column("semantic_prompt", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("localization_glossaries", "semantic_prompt")
