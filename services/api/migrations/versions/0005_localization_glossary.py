"""Tenant-managed Goals Localization glossary.

Revision ID: 0005_localization_glossary
Revises: 0004_goals_localization
Create Date: 2026-11-11
"""

from collections.abc import Sequence

from alembic import op

import app.models  # noqa: F401
from app.db.base import Base

revision: str = "0005_localization_glossary"
down_revision: str | None = "0004_goals_localization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Base.metadata.create_all(
        op.get_bind(),
        tables=[Base.metadata.tables["localization_glossaries"]],
        checkfirst=True,
    )


def downgrade() -> None:
    op.drop_table("localization_glossaries")
