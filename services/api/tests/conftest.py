from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

from app.api.v1.auth import login_limiter
from app.core.config import get_settings
from app.db.session import create_session_factory, get_engine, reset_engine_cache
from app.main import create_app
from app.models.auth import MembershipRole
from app.services import auth_service


def _point_tests_at_isolated_database() -> None:
    """Tests truncate tables. Never let that run against the app database."""
    get_settings.cache_clear()
    url = make_url(get_settings().database_url)
    database = url.database or ""
    if database.endswith("_test"):
        return
    test_name = f"{database}_test"
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": test_name},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{test_name}"'))
    admin.dispose()
    os.environ["DATABASE_URL"] = url.set(database=test_name).render_as_string(hide_password=False)
    get_settings.cache_clear()
    reset_engine_cache()
    api_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "migrations"))
    command.upgrade(cfg, "head")


_point_tests_at_isolated_database()


@pytest.fixture(autouse=True)
def _clean_db() -> None:
    reset_engine_cache()
    get_settings.cache_clear()
    login_limiter.clear()
    engine = get_engine()
    if not str(engine.url.database or "").endswith("_test"):
        raise RuntimeError("Refusing to wipe a non-test database.")
    with engine.begin() as conn:
        conn.execute(text("SET app.bypass_rls = 'on'"))
        for table in (
            "evidence_items",
            "candidate_results",
            "export_jobs",
            "usage_events",
            "evaluation_runs",
            "job_profile_versions",
            "job_profiles",
            "ingestion_batch_items",
            "ingestion_batches",
            "outbox_events",
            "resume_versions",
            "resumes",
            "pricing_versions",
            "audit_events",
            "password_reset_tokens",
            "email_verification_tokens",
            "invitations",
            "sessions",
            "tenant_memberships",
            "users",
            "tenants",
        ):
            conn.execute(text(f"TRUNCATE {table} CASCADE"))
    yield
    login_limiter.clear()
    get_settings.cache_clear()
    reset_engine_cache()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def two_tenants():
    db = create_session_factory(get_engine())()
    try:
        a = auth_service.create_tenant(db, name="Tenant A", slug="tenant-a")
        b = auth_service.create_tenant(db, name="Tenant B", slug="tenant-b")
        admin_a = auth_service.create_user(
            db,
            email="admin-a@example.com",
            password="PasswordA-12345",
            is_email_verified=True,
        )
        admin_b = auth_service.create_user(
            db,
            email="admin-b@example.com",
            password="PasswordB-12345",
            is_email_verified=True,
        )
        viewer_a = auth_service.create_user(
            db,
            email="viewer-a@example.com",
            password="PasswordV-12345",
            is_email_verified=True,
        )
        auth_service.add_membership(
            db, tenant_id=a.id, user_id=admin_a.id, role=MembershipRole.tenant_admin
        )
        auth_service.add_membership(
            db, tenant_id=b.id, user_id=admin_b.id, role=MembershipRole.tenant_admin
        )
        auth_service.add_membership(
            db, tenant_id=a.id, user_id=viewer_a.id, role=MembershipRole.viewer
        )
        db.commit()
        yield {
            "tenant_a": a,
            "tenant_b": b,
            "admin_a": admin_a,
            "admin_b": admin_b,
            "viewer_a": viewer_a,
        }
    finally:
        db.close()


def login(client: TestClient, email: str, password: str, tenant_slug: str | None = None):
    payload = {"email": email, "password": password}
    if tenant_slug:
        payload["tenant_slug"] = tenant_slug
    response = client.post("/api/v1/auth/login", json=payload)
    return response
