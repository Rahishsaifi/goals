from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import create_session_factory, get_engine
from app.models.auth import MembershipRole, PasswordResetToken, Session
from app.services import auth_service
from tests.conftest import login


def test_login_sets_http_only_session_cookie(client: TestClient, two_tenants) -> None:
    response = login(client, "admin-a@example.com", "PasswordA-12345", "tenant-a")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "admin-a@example.com"
    assert body["active_tenant_id"] == str(two_tenants["tenant_a"].id)
    assert "password" not in body
    assert "password_hash" not in response.text
    assert client.cookies.get("ri_session")
    assert client.cookies.get("ri_csrf")


def test_me_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_unverified_user_cannot_login(client: TestClient, two_tenants) -> None:
    db = create_session_factory(get_engine())()
    try:
        user = auth_service.create_user(
            db, email="new@example.com", password="PasswordN-12345", is_email_verified=False
        )
        auth_service.add_membership(
            db,
            tenant_id=two_tenants["tenant_a"].id,
            user_id=user.id,
            role=MembershipRole.recruiter,
        )
        db.commit()
    finally:
        db.close()
    response = login(client, "new@example.com", "PasswordN-12345", "tenant-a")
    assert response.status_code == 403


def test_disabled_user_cannot_login(client: TestClient, two_tenants) -> None:
    db = create_session_factory(get_engine())()
    try:
        user = two_tenants["admin_a"]
        db_user = db.get(type(user), user.id)
        assert db_user is not None
        db_user.is_disabled = True
        db.commit()
    finally:
        db.close()
    response = login(client, "admin-a@example.com", "PasswordA-12345", "tenant-a")
    assert response.status_code == 403


def test_wrong_password_is_generic(client: TestClient, two_tenants) -> None:
    del two_tenants
    response = login(client, "admin-a@example.com", "wrong-password-xx", "tenant-a")
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid email or password."


def test_cross_tenant_login_denied(client: TestClient, two_tenants) -> None:
    del two_tenants
    response = login(client, "admin-a@example.com", "PasswordA-12345", "tenant-b")
    assert response.status_code == 403


def test_viewer_cannot_create_invitation(client: TestClient, two_tenants) -> None:
    del two_tenants
    assert login(client, "viewer-a@example.com", "PasswordV-12345", "tenant-a").status_code == 200
    csrf = client.cookies.get("ri_csrf")
    response = client.post(
        "/api/v1/auth/invitations",
        json={"email": "hire@example.com", "role": "recruiter"},
        headers={"x-csrf-token": csrf or ""},
    )
    assert response.status_code == 403


def test_csrf_required_for_logout(client: TestClient, two_tenants) -> None:
    del two_tenants
    assert login(client, "admin-a@example.com", "PasswordA-12345", "tenant-a").status_code == 200
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 403


def test_logout_revokes_session(client: TestClient, two_tenants) -> None:
    del two_tenants
    assert login(client, "admin-a@example.com", "PasswordA-12345", "tenant-a").status_code == 200
    csrf = client.cookies.get("ri_csrf")
    logout = client.post("/api/v1/auth/logout", headers={"x-csrf-token": csrf or ""})
    assert logout.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_invitation_and_email_verification_flow(client: TestClient, two_tenants) -> None:
    del two_tenants
    assert login(client, "admin-a@example.com", "PasswordA-12345", "tenant-a").status_code == 200
    csrf = client.cookies.get("ri_csrf")
    invite = client.post(
        "/api/v1/auth/invitations",
        json={"email": "recruiter@example.com", "role": "recruiter"},
        headers={"x-csrf-token": csrf or ""},
    )
    assert invite.status_code == 200
    token = invite.json()["invite_token"]
    assert token
    accept = client.post(
        "/api/v1/auth/accept-invitation",
        json={
            "token": token,
            "email": "recruiter@example.com",
            "password": "RecruiterPass-123",
        },
    )
    assert accept.status_code == 200
    # Verify email via service-issued token for the new user.
    db = create_session_factory(get_engine())()
    try:
        from app.models.auth import User

        user = db.scalar(select(User).where(User.email_normalized == "recruiter@example.com"))
        assert user is not None
        verify_token = auth_service.issue_email_verification_token(
            db, user, get_settings_for_test()
        )
        db.commit()
    finally:
        db.close()
    assert (
        client.post("/api/v1/auth/verify-email", json={"token": verify_token}).status_code == 200
    )
    assert (
        login(client, "recruiter@example.com", "RecruiterPass-123", "tenant-a").status_code == 200
    )


def get_settings_for_test():
    from app.core.config import get_settings

    return get_settings()


def test_password_reset_is_single_use(client: TestClient, two_tenants) -> None:
    del two_tenants
    db = create_session_factory(get_engine())()
    try:
        token = auth_service.request_password_reset(
            db, email="admin-a@example.com", settings=get_settings_for_test()
        )
        db.commit()
    finally:
        db.close()
    assert token
    first = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "password": "NewPassword-12345"},
    )
    assert first.status_code == 200
    second = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "password": "AnotherPassword-99"},
    )
    assert second.status_code == 400
    assert login(client, "admin-a@example.com", "NewPassword-12345", "tenant-a").status_code == 200


def test_expired_password_reset_rejected(client: TestClient, two_tenants) -> None:
    user = two_tenants["admin_a"]
    db = create_session_factory(get_engine())()
    try:
        from app.security.tokens import generate_token, hash_token

        raw = generate_token()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(raw),
                expires_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        db.commit()
    finally:
        db.close()
    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw, "password": "FreshPassword-123"},
    )
    assert response.status_code == 400


def test_login_rate_limit(client: TestClient, two_tenants) -> None:
    del two_tenants
    from app.api.v1.auth import login_limiter

    login_limiter.clear()
    # Force a tiny limit for this test.
    login_limiter.limit = 3
    try:
        for _ in range(3):
            login(client, "admin-a@example.com", "wrong-password", "tenant-a")
        limited = login(client, "admin-a@example.com", "wrong-password", "tenant-a")
        assert limited.status_code == 429
    finally:
        login_limiter.limit = 10
        login_limiter.clear()


def test_forged_tenant_slug_does_not_grant_access(client: TestClient, two_tenants) -> None:
    del two_tenants
    response = login(client, "admin-a@example.com", "PasswordA-12345", "tenant-b")
    assert response.status_code == 403


def test_revoked_session_rejected(client: TestClient, two_tenants) -> None:
    del two_tenants
    assert login(client, "admin-a@example.com", "PasswordA-12345", "tenant-a").status_code == 200
    db = create_session_factory(get_engine())()
    try:
        sessions = db.scalars(select(Session)).all()
        for session in sessions:
            session.revoked_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_password_hash_never_returned(client: TestClient, two_tenants) -> None:
    del two_tenants
    response = login(client, "admin-a@example.com", "PasswordA-12345", "tenant-a")
    assert "argon2" not in response.text.lower()
    me = client.get("/api/v1/auth/me")
    assert "argon2" not in me.text.lower()
    assert "password_hash" not in me.text


def test_tenant_admin_is_not_platform_admin(client: TestClient, two_tenants) -> None:
    del two_tenants
    response = login(client, "admin-a@example.com", "PasswordA-12345", "tenant-a")
    assert response.status_code == 200
    assert response.json()["is_platform_admin"] is False
