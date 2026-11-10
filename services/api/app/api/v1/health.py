from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from recruitment_contracts import HealthResponse
from sqlalchemy.engine import Engine

from app.db.session import database_is_ready

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
def ready(request: Request) -> JSONResponse:
    engine: Engine = request.app.state.engine
    database_ok = database_is_ready(engine)
    status: Literal["ok", "unavailable"] = "ok" if database_ok else "unavailable"
    body = HealthResponse(
        status=status,
        checks={"database": "ok" if database_ok else "unavailable"},
    )
    return JSONResponse(status_code=200 if database_ok else 503, content=body.model_dump())
