from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.models.auth import (
    AuditEvent,
    EmailVerificationToken,
    Invitation,
    MembershipRole,
    PasswordResetToken,
    Tenant,
    TenantMembership,
    User,
)
from app.models.auth import (
    Session as AuthSession,
)
from app.security.passwords import hash_password, normalize_email, verify_password
from app.security.tokens import generate_token, hash_token


class AuthError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


GENERIC_AUTH_FAILURE = AuthError(
    "invalid_credentials",
    "Invalid email or password.",
    status_code=401,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def create_tenant(db: Session, *, name: str, slug: str) -> Tenant:
    tenant = Tenant(name=name, slug=slug)
    db.add(tenant)
    db.flush()
    return tenant


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    is_email_verified: bool = False,
    is_platform_admin: bool = False,
) -> User:
    normalized = normalize_email(email)
    existing = db.scalar(select(User).where(User.email_normalized == normalized))
    if existing is not None:
        raise AuthError("email_taken", "Unable to create account.", status_code=409)
    user = User(
        email=email.strip(),
        email_normalized=normalized,
        password_hash=hash_password(password),
        is_email_verified=is_email_verified,
        is_platform_admin=is_platform_admin,
    )
    db.add(user)
    db.flush()
    return user


def add_membership(
    db: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID, role: MembershipRole
) -> TenantMembership:
    membership = TenantMembership(tenant_id=tenant_id, user_id=user_id, role=role)
    db.add(membership)
    db.flush()
    return membership


def authenticate(
    db: Session,
    *,
    email: str,
    password: str,
    tenant_slug: str | None,
    settings: Settings,
) -> tuple[User, AuthSession, str, str]:
    normalized = normalize_email(email)
    user = db.scalar(
        select(User)
        .where(User.email_normalized == normalized)
        .options(selectinload(User.memberships).selectinload(TenantMembership.tenant))
    )
    if user is None or not verify_password(user.password_hash, password):
        raise GENERIC_AUTH_FAILURE
    if user.is_disabled:
        raise AuthError("account_disabled", "Account is disabled.", status_code=403)
    if not user.is_email_verified:
        raise AuthError("email_unverified", "Email verification is required.", status_code=403)

    tenant_id: uuid.UUID | None = None
    if tenant_slug:
        membership = next(
            (m for m in user.memberships if m.tenant.slug == tenant_slug and m.tenant.is_active),
            None,
        )
        if membership is None and not user.is_platform_admin:
            raise AuthError("tenant_forbidden", "Access denied.", status_code=403)
        if membership is not None:
            tenant_id = membership.tenant_id
    elif user.memberships:
        active = next((m for m in user.memberships if m.tenant.is_active), None)
        if active is not None:
            tenant_id = active.tenant_id

    session_token = generate_token()
    csrf_token = generate_token()
    session = AuthSession(
        user_id=user.id,
        tenant_id=tenant_id,
        token_hash=hash_token(session_token),
        csrf_token_hash=hash_token(csrf_token),
        expires_at=_utcnow() + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(session)
    db.add(
        AuditEvent(
            tenant_id=tenant_id,
            actor_user_id=user.id,
            action="auth.login",
            resource_type="session",
        )
    )
    db.flush()
    return user, session, session_token, csrf_token


def resolve_session(db: Session, *, session_token: str) -> AuthSession | None:
    session = db.scalar(
        select(AuthSession)
        .where(AuthSession.token_hash == hash_token(session_token))
        .options(
            selectinload(AuthSession.user).selectinload(User.memberships).selectinload(
                TenantMembership.tenant
            )
        )
    )
    if session is None:
        return None
    if session.revoked_at is not None:
        return None
    if session.expires_at <= _utcnow():
        return None
    if session.user.is_disabled:
        return None
    return session


def revoke_session(db: Session, session: AuthSession) -> None:
    session.revoked_at = _utcnow()
    db.add(
        AuditEvent(
            tenant_id=session.tenant_id,
            actor_user_id=session.user_id,
            action="auth.logout",
            resource_type="session",
            resource_id=str(session.id),
        )
    )
    db.flush()


def create_invitation(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    email: str,
    role: MembershipRole,
    created_by_user_id: uuid.UUID | None,
    settings: Settings,
) -> tuple[Invitation, str]:
    if role == MembershipRole.platform_admin:
        raise AuthError("invalid_role", "Platform admin cannot be invited into a tenant.")
    token = generate_token()
    invitation = Invitation(
        tenant_id=tenant_id,
        email_normalized=normalize_email(email),
        role=role,
        token_hash=hash_token(token),
        expires_at=_utcnow() + timedelta(hours=settings.invitation_ttl_hours),
        created_by_user_id=created_by_user_id,
    )
    db.add(invitation)
    db.flush()
    return invitation, token


def accept_invitation(
    db: Session, *, token: str, email: str, password: str, settings: Settings
) -> User:
    if len(password) < settings.min_password_length:
        raise AuthError("weak_password", "Password does not meet policy.")
    invitation = db.scalar(
        select(Invitation).where(Invitation.token_hash == hash_token(token))
    )
    if (
        invitation is None
        or invitation.accepted_at is not None
        or invitation.expires_at <= _utcnow()
    ):
        raise AuthError("invalid_invitation", "Invitation is invalid or expired.", status_code=400)
    if invitation.email_normalized != normalize_email(email):
        raise AuthError("invalid_invitation", "Invitation is invalid or expired.", status_code=400)

    user = create_user(db, email=email, password=password, is_email_verified=False)
    add_membership(db, tenant_id=invitation.tenant_id, user_id=user.id, role=invitation.role)
    invitation.accepted_at = _utcnow()
    verify_token = generate_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(verify_token),
            expires_at=_utcnow() + timedelta(hours=settings.email_verification_ttl_hours),
        )
    )
    # Attach raw verification token for local tests via audit details is avoided;
    # callers that need it should use issue_email_verification_token.
    db.flush()
    user._pending_verification_token = verify_token  # type: ignore[attr-defined]
    return user


def issue_email_verification_token(db: Session, user: User, settings: Settings) -> str:
    token = generate_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=_utcnow() + timedelta(hours=settings.email_verification_ttl_hours),
        )
    )
    db.flush()
    return token


def verify_email(db: Session, *, token: str) -> None:
    record = db.scalar(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == hash_token(token)
        )
    )
    if record is None or record.used_at is not None or record.expires_at <= _utcnow():
        raise AuthError("invalid_token", "Verification token is invalid or expired.")
    user = db.get(User, record.user_id)
    if user is None:
        raise AuthError("invalid_token", "Verification token is invalid or expired.")
    user.is_email_verified = True
    record.used_at = _utcnow()
    db.flush()


def request_password_reset(db: Session, *, email: str, settings: Settings) -> str | None:
    user = db.scalar(select(User).where(User.email_normalized == normalize_email(email)))
    if user is None or user.is_disabled:
        return None
    token = generate_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=_utcnow() + timedelta(hours=settings.password_reset_ttl_hours),
        )
    )
    db.flush()
    return token


def reset_password(db: Session, *, token: str, password: str, settings: Settings) -> None:
    if len(password) < settings.min_password_length:
        raise AuthError("weak_password", "Password does not meet policy.")
    record = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token))
    )
    if record is None or record.used_at is not None or record.expires_at <= _utcnow():
        raise AuthError("invalid_token", "Reset token is invalid or expired.")
    user = db.get(User, record.user_id)
    if user is None or user.is_disabled:
        raise AuthError("invalid_token", "Reset token is invalid or expired.")
    user.password_hash = hash_password(password)
    record.used_at = _utcnow()
    # Revoke all sessions on password reset.
    sessions = db.scalars(select(AuthSession).where(AuthSession.user_id == user.id)).all()
    now = _utcnow()
    for session in sessions:
        if session.revoked_at is None:
            session.revoked_at = now
    db.flush()


def membership_for_tenant(user: User, tenant_id: uuid.UUID) -> TenantMembership | None:
    return next((m for m in user.memberships if m.tenant_id == tenant_id), None)
