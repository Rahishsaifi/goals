from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import DbSession, require_roles
from app.models.auth import MembershipRole
from app.security.auth_context import AuthContext
from app.services import usage_service

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/summary")
def summary(
    db: DbSession,
    auth: Annotated[
        AuthContext,
        Depends(
            require_roles(
                MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer
            )
        ),
    ],
) -> dict[str, object]:
    if auth.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    return usage_service.usage_summary(db, tenant_id=auth.tenant_id)


@router.get("/events")
def events(
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
    rows = usage_service.list_usage_events(db, tenant_id=auth.tenant_id)
    return [
        {
            "id": row.id,
            "operation_type": row.operation_type,
            "provider": row.provider,
            "model_deployment": row.model_deployment,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "embedding_tokens": row.embedding_tokens,
            "estimated_total_cost": str(row.estimated_total_cost)
            if row.estimated_total_cost is not None
            else None,
            "usage_available": row.usage_available,
            "status": row.status,
        }
        for row in rows
    ]


@router.get("/pricing")
def pricing(
    auth: Annotated[
        AuthContext,
        Depends(
            require_roles(
                MembershipRole.tenant_admin, MembershipRole.recruiter, MembershipRole.viewer
            )
        ),
    ],
) -> dict[str, object]:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.model_provider == "foundry":
        return {
            "provider": "foundry",
            "deployment": settings.azure_openai_deployment,
            "note": "Live Azure OpenAI pay-per-token. POC budget alert is USD $10 on rg-meridian-poc.",
            "rates_per_million_tokens": {
                "input": "see Azure pricing for gpt-4.1-mini",
                "output": "see Azure pricing for gpt-4.1-mini",
                "embedding": "n/a",
            },
            "currency": "USD",
            "budget_usd": 10,
        }
    del auth
    return {
        "provider": "mock",
        "note": "Mock pricing only. Set MODEL_PROVIDER=foundry for live Azure OpenAI.",
        "rates_per_million_tokens": {
            "input": "0",
            "output": "0",
            "embedding": "0",
        },
        "currency": "USD",
    }
