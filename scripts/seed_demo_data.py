#!/usr/bin/env python3
"""Provision the local POC tenant, administrator, and sample job profiles."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import create_session_factory, get_engine
from app.integrations.model_provider import MockModelProvider
from app.models.auth import MembershipRole, Tenant, User
from app.models.domain import JobProfile
from app.security.passwords import hash_password, normalize_email
from app.services import auth_service, job_service

DEMO_EMAIL = "demo@demo.com"
DEMO_PASSWORD = "admin123"
LEGACY_ADMIN_EMAIL = "admin@example.com"

SOFTWARE_DEV_PROFILES: list[dict[str, str]] = [
    {
        "title": "Software Developer",
        "source_text": (
            "We are hiring a Software Developer to build and maintain web services. "
            "Required: Python or TypeScript, REST APIs, relational databases (PostgreSQL), "
            "Git, unit testing. Preferred: Docker, CI/CD, cloud basics (Azure or AWS). "
            "3+ years experience building production applications."
        ),
    },
    {
        "title": "Senior Software Developer",
        "source_text": (
            "Senior Software Developer to lead feature delivery and mentor engineers. "
            "Required: strong system design, Python/TypeScript, distributed services, "
            "SQL performance tuning, code review leadership. Preferred: Kubernetes, "
            "event-driven architecture, observability. 6+ years experience."
        ),
    },
    {
        "title": "Full Stack Software Developer",
        "source_text": (
            "Full Stack Software Developer for product squads. Required: React/Next.js, "
            "Node.js or Python FastAPI, PostgreSQL, responsive UI, API design. "
            "Preferred: Tailwind CSS, auth/session security, Azure deployment experience. "
            "4+ years full-stack delivery."
        ),
    },
    {
        "title": "Backend Software Developer",
        "source_text": (
            "Backend Software Developer focused on APIs and data pipelines. "
            "Required: Python, FastAPI or similar, PostgreSQL, message queues, "
            "idempotent job processing. Preferred: Azure Service Bus, blob storage, "
            "search indexing. 3+ years backend experience."
        ),
    },
    {
        "title": "Frontend Software Developer",
        "source_text": (
            "Frontend Software Developer for recruiter-facing product UI. "
            "Required: TypeScript, React, Next.js App Router, accessible forms, "
            "CSS design systems. Preferred: charting, performance profiling, "
            "end-to-end testing. 3+ years frontend experience."
        ),
    },
]


def _ensure_admin(db, tenant: Tenant) -> User:
    admin = db.scalar(
        select(User).where(User.email_normalized == normalize_email(DEMO_EMAIL))
    )
    if admin is None:
        legacy = db.scalar(
            select(User).where(User.email_normalized == normalize_email(LEGACY_ADMIN_EMAIL))
        )
        if legacy is not None:
            legacy.email = DEMO_EMAIL
            legacy.email_normalized = normalize_email(DEMO_EMAIL)
            legacy.password_hash = hash_password(DEMO_PASSWORD)
            legacy.is_email_verified = True
            legacy.is_disabled = False
            admin = legacy
        else:
            admin = auth_service.create_user(
                db,
                email=DEMO_EMAIL,
                password=DEMO_PASSWORD,
                is_email_verified=True,
                is_platform_admin=False,
            )
    else:
        admin.password_hash = hash_password(DEMO_PASSWORD)
        admin.is_email_verified = True
        admin.is_disabled = False

    membership = next((m for m in admin.memberships if m.tenant_id == tenant.id), None)
    if membership is None:
        # memberships may not be loaded; query via add if missing
        from app.models.auth import TenantMembership

        existing = db.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant.id,
                TenantMembership.user_id == admin.id,
            )
        )
        if existing is None:
            auth_service.add_membership(
                db,
                tenant_id=tenant.id,
                user_id=admin.id,
                role=MembershipRole.tenant_admin,
            )
    db.flush()
    return admin


def main() -> int:
    settings = get_settings()
    session_factory = create_session_factory(get_engine())
    db = session_factory()
    provider = MockModelProvider()
    try:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == "demo"))
        if tenant is None:
            tenant = auth_service.create_tenant(db, name="Demo Client", slug="demo")
        admin = _ensure_admin(db, tenant)

        created: list[str] = []
        skipped: list[str] = []
        for item in SOFTWARE_DEV_PROFILES:
            exists = db.scalar(
                select(JobProfile).where(
                    JobProfile.tenant_id == tenant.id,
                    JobProfile.title == item["title"],
                )
            )
            if exists is not None:
                skipped.append(item["title"])
                continue
            job_service.create_job_profile(
                db,
                tenant_id=tenant.id,
                user_id=admin.id,
                title=item["title"],
                source_text=item["source_text"],
                criteria=None,
                provider=provider,
            )
            created.append(item["title"])

        db.commit()
        print(
            {
                "tenant_slug": tenant.slug,
                "admin_email": DEMO_EMAIL,
                "password": DEMO_PASSWORD,
                "app_env": settings.app_env,
                "job_profiles_created": created,
                "job_profiles_skipped": skipped,
                "note": "Local seed only. Change the password before any shared use.",
            }
        )
        return 0
    except Exception as exc:
        db.rollback()
        print({"error": str(exc)})
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
