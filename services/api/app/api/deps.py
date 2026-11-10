from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.auth import MembershipRole
from app.security.auth_context import AuthContext
from app.security.tokens import hash_token
from app.services import auth_service

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_optional_auth(
    request: Request,
    db: DbSession,
    settings: AppSettings,
) -> AuthContext | None:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    session = auth_service.resolve_session(db, session_token=token)
    if session is None:
        return None
    role: MembershipRole | None = None
    if session.tenant_id is not None:
        membership = auth_service.membership_for_tenant(session.user, session.tenant_id)
        role = membership.role if membership else None
        if membership is None and not session.user.is_platform_admin:
            return None
    csrf_cookie = request.cookies.get(settings.csrf_cookie_name, "")
    return AuthContext(
        user_id=session.user_id,
        session_id=session.id,
        tenant_id=session.tenant_id,
        role=role,
        is_platform_admin=session.user.is_platform_admin,
        is_email_verified=session.user.is_email_verified,
        csrf_token=csrf_cookie,
    )


def require_auth(
    auth: Annotated[AuthContext | None, Depends(get_optional_auth)],
) -> AuthContext:
    if auth is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return auth


def require_csrf(
    request: Request,
    auth: Annotated[AuthContext, Depends(require_auth)],
    settings: AppSettings,
    db: DbSession,
) -> AuthContext:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return auth
    provided = request.headers.get(settings.csrf_header_name)
    cookie = request.cookies.get(settings.csrf_cookie_name)
    if not provided or not cookie or provided != cookie:
        raise HTTPException(status_code=403, detail="CSRF validation failed.")
    session = auth_service.resolve_session(
        db, session_token=request.cookies.get(settings.session_cookie_name, "")
    )
    if session is None or session.csrf_token_hash != hash_token(cookie):
        raise HTTPException(status_code=403, detail="CSRF validation failed.")
    return auth


def require_roles(*roles: MembershipRole) -> Callable[[AuthContext], AuthContext]:
    allowed = set(roles)

    def _dependency(auth: Annotated[AuthContext, Depends(require_auth)]) -> AuthContext:
        if auth.is_platform_admin:
            return auth
        if auth.role is None or auth.role not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient permissions.")
        return auth

    return _dependency


def require_tenant_admin(
    auth: Annotated[
        AuthContext,
        Depends(require_roles(MembershipRole.tenant_admin)),
    ],
) -> AuthContext:
    if auth.tenant_id is None and not auth.is_platform_admin:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    return auth
