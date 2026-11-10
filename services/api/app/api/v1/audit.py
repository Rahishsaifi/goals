from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import DbSession, require_roles
from app.models.auth import AuditEvent, MembershipRole, User
from app.security.auth_context import AuthContext

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def list_audit_events(
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(
            require_roles(
                MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer
            )
        ),
    ],
) -> list[dict[str, object]]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    rows = db.execute(
        select(AuditEvent, User.email)
        .outerjoin(User, User.id == AuditEvent.actor_user_id)
        .where(AuditEvent.tenant_id == auth.tenant_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(200)
    ).all()
    return [
        {
            "id": event.id,
            "action": event.action,
            "actor_email": email,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        for event, email in rows
    ]
