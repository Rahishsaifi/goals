from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.models.auth import MembershipRole


@dataclass(frozen=True)
class AuthContext:
    user_id: uuid.UUID
    session_id: uuid.UUID
    tenant_id: uuid.UUID | None
    role: MembershipRole | None
    is_platform_admin: bool
    is_email_verified: bool
    csrf_token: str

    def require_tenant(self) -> uuid.UUID:
        if self.tenant_id is None:
            raise PermissionError("tenant_required")
        return self.tenant_id
