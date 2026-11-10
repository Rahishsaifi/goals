from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.v1.audit import router as audit_router
from app.api.v1.auth import router as auth_router
from app.api.v1.evaluations import router as evaluations_router
from app.api.v1.goals_localization import router as goals_localization_router
from app.api.v1.health import router as health_router
from app.api.v1.job_profiles import router as job_profiles_router
from app.api.v1.resumes import router as resumes_router
from app.api.v1.usage import router as usage_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_engine, reset_engine_cache
from app.middleware.correlation import CorrelationIdMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="Recruitment Intelligence API", version="0.1.0")
    reset_engine_cache()
    app.state.engine = get_engine()
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(resumes_router, prefix="/api/v1")
    app.include_router(job_profiles_router, prefix="/api/v1")
    app.include_router(evaluations_router, prefix="/api/v1")
    app.include_router(goals_localization_router, prefix="/api/v1")
    app.include_router(usage_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    return app


app = create_app()
