"""Goals Library Localization tables.

Revision ID: 0004_goals_localization
Revises: 0003_domain_core
Create Date: 2026-11-10
"""

from collections.abc import Sequence

from alembic import op

import app.models  # noqa: F401
from app.db.base import Base

revision: str = "0004_goals_localization"
down_revision: str | None = "0003_domain_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = [
    "localization_jobs",
    "localization_records",
    "localization_qa_results",
    "translation_cache_entries",
]


def upgrade() -> None:
    tables = [Base.metadata.tables[name] for name in _TABLES]
    Base.metadata.create_all(op.get_bind(), tables=tables, checkfirst=True)


def downgrade() -> None:
    for name in reversed(_TABLES):
        op.drop_table(name)
