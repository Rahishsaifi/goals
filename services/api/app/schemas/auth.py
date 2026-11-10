from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.auth import MembershipRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)
    tenant_slug: str | None = None


class AcceptInvitationRequest(BaseModel):
    token: str
    password: str = Field(min_length=12, max_length=128)
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=12, max_length=128)


class InviteUserRequest(BaseModel):
    email: EmailStr
    role: MembershipRole


class MembershipOut(BaseModel):
    tenant_id: UUID
    tenant_slug: str
    tenant_name: str
    role: MembershipRole


class MeResponse(BaseModel):
    id: UUID
    email: str
    is_email_verified: bool
    is_platform_admin: bool
    active_tenant_id: UUID | None
    memberships: list[MembershipOut]


class AuthMessage(BaseModel):
    message: str


class InviteCreatedResponse(BaseModel):
    invitation_id: UUID
    email: str
    role: MembershipRole
    expires_at: datetime
    # Returned only in local/test so the seed and tests can accept invites without email delivery.
    invite_token: str | None = None
