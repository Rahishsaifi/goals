from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import (
    AppSettings,
    DbSession,
    require_auth,
    require_csrf,
    require_tenant_admin,
)
from app.models.auth import MembershipRole, TenantMembership, User
from app.schemas.auth import (
    AcceptInvitationRequest,
    AuthMessage,
    ForgotPasswordRequest,
    InviteCreatedResponse,
    InviteUserRequest,
    LoginRequest,
    MembershipOut,
    MeResponse,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from app.security.auth_context import AuthContext
from app.security.rate_limit import SlidingWindowRateLimiter
from app.services import auth_service
from app.services.auth_service import AuthError

router = APIRouter(prefix="/auth", tags=["auth"])
login_limiter = SlidingWindowRateLimiter(limit=10, window_seconds=300)


def _set_auth_cookies(
    response: Response,
    *,
    session_token: str,
    csrf_token: str,
    settings: AppSettings,
) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


def _clear_auth_cookies(response: Response, settings: AppSettings) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


def _raise_auth_error(exc: AuthError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post("/login", response_model=MeResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> MeResponse:
    client = request.client.host if request.client else "unknown"
    limit = login_limiter.check(f"{client}:{payload.email.lower()}")
    if not limit.allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts.",
            headers={"Retry-After": str(limit.retry_after_seconds)},
        )
    try:
        user, session, session_token, csrf_token = auth_service.authenticate(
            db,
            email=payload.email,
            password=payload.password,
            tenant_slug=payload.tenant_slug,
            settings=settings,
        )
        db.commit()
    except AuthError as exc:
        db.rollback()
        _raise_auth_error(exc)
    _set_auth_cookies(
        response, session_token=session_token, csrf_token=csrf_token, settings=settings
    )
    return _me_response(db, user_id=user.id, active_tenant_id=session.tenant_id)


@router.post("/logout", response_model=AuthMessage)
def logout(
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
    auth: Annotated[AuthContext, Depends(require_csrf)],
) -> AuthMessage:
    token = request.cookies.get(settings.session_cookie_name, "")
    session = auth_service.resolve_session(db, session_token=token)
    if session is not None:
        auth_service.revoke_session(db, session)
        db.commit()
    _clear_auth_cookies(response, settings)
    return AuthMessage(message="Logged out.")


@router.get("/me", response_model=MeResponse)
def me(
    db: DbSession,
    auth: Annotated[AuthContext, Depends(require_auth)],
) -> MeResponse:
    return _me_response(db, user_id=auth.user_id, active_tenant_id=auth.tenant_id)


@router.post("/accept-invitation", response_model=AuthMessage)
def accept_invitation(
    payload: AcceptInvitationRequest,
    db: DbSession,
    settings: AppSettings,
) -> AuthMessage:
    try:
        auth_service.accept_invitation(
            db,
            token=payload.token,
            email=payload.email,
            password=payload.password,
            settings=settings,
        )
        db.commit()
    except AuthError as exc:
        db.rollback()
        _raise_auth_error(exc)
    return AuthMessage(message="Invitation accepted. Verify your email before signing in.")


@router.post("/verify-email", response_model=AuthMessage)
def verify_email(payload: VerifyEmailRequest, db: DbSession) -> AuthMessage:
    try:
        auth_service.verify_email(db, token=payload.token)
        db.commit()
    except AuthError as exc:
        db.rollback()
        _raise_auth_error(exc)
    return AuthMessage(message="Email verified.")


@router.post("/forgot-password", response_model=AuthMessage)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: DbSession,
    settings: AppSettings,
) -> AuthMessage:
    # Always return the same message to avoid account enumeration.
    auth_service.request_password_reset(db, email=payload.email, settings=settings)
    db.commit()
    return AuthMessage(message="If the account exists, a reset link was issued.")


@router.post("/reset-password", response_model=AuthMessage)
def reset_password(
    payload: ResetPasswordRequest,
    db: DbSession,
    settings: AppSettings,
) -> AuthMessage:
    try:
        auth_service.reset_password(
            db, token=payload.token, password=payload.password, settings=settings
        )
        db.commit()
    except AuthError as exc:
        db.rollback()
        _raise_auth_error(exc)
    return AuthMessage(message="Password updated.")


@router.post("/invitations", response_model=InviteCreatedResponse)
def create_invitation(
    payload: InviteUserRequest,
    db: DbSession,
    settings: AppSettings,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    _: Annotated[AuthContext, Depends(require_tenant_admin)],
) -> InviteCreatedResponse:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    try:
        invitation, token = auth_service.create_invitation(
            db,
            tenant_id=auth.tenant_id,
            email=payload.email,
            role=payload.role,
            created_by_user_id=auth.user_id,
            settings=settings,
        )
        db.commit()
    except AuthError as exc:
        db.rollback()
        _raise_auth_error(exc)
    return InviteCreatedResponse(
        invitation_id=invitation.id,
        email=payload.email,
        role=payload.role,
        expires_at=invitation.expires_at,
        invite_token=token if settings.app_env in {"local", "test"} else None,
    )


def _me_response(
    db: DbSession, *, user_id: uuid.UUID, active_tenant_id: uuid.UUID | None
) -> MeResponse:
    user = db.scalar(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.memberships).selectinload(TenantMembership.tenant))
    )
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    memberships = [
        MembershipOut(
            tenant_id=m.tenant_id,
            tenant_slug=m.tenant.slug,
            tenant_name=m.tenant.name,
            role=m.role,
        )
        for m in user.memberships
        if m.role != MembershipRole.platform_admin
    ]
    return MeResponse(
        id=user.id,
        email=user.email,
        is_email_verified=user.is_email_verified,
        is_platform_admin=user.is_platform_admin,
        active_tenant_id=active_tenant_id,
        memberships=memberships,
    )
