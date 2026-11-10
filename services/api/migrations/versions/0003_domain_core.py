"""Domain tables for ingestion, jobs, evaluation, and usage.

Revision ID: 0003_domain_core
Revises: 0002_auth_tenancy
Create Date: 2026-10-10
"""

from collections.abc import Sequence

from alembic import op

import app.models  # noqa: F401
from app.db.base import Base

revision: str = "0003_domain_core"
down_revision: str | None = "0002_auth_tenancy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = [
    "resumes",
    "resume_versions",
    "ingestion_batches",
    "ingestion_batch_items",
    "outbox_events",
    "job_profiles",
    "job_profile_versions",
    "evaluation_runs",
    "candidate_results",
    "evidence_items",
    "usage_events",
    "pricing_versions",
    "export_jobs",
]


def upgrade() -> None:
    tables = [Base.metadata.tables[name] for name in _TABLES]
    Base.metadata.create_all(op.get_bind(), tables=tables, checkfirst=True)


def downgrade() -> None:
    for name in reversed(_TABLES):
        op.drop_table(name)
