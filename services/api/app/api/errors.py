import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from recruitment_contracts import ErrorBody, ErrorResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return _error_response(
            request,
            status_code=exc.status_code,
            code="http_error",
            message=_safe_http_message(exc),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            request,
            status_code=422,
            code="validation_error",
            message=_validation_message(exc),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", extra={"request_id": _request_id(request)})
        del exc
        return _error_response(
            request,
            status_code=500,
            code="internal_error",
            message="The request could not be completed.",
        )


def _validation_message(exc: RequestValidationError) -> str:
    for err in exc.errors():
        if err.get("type") == "string_too_long":
            max_length = (err.get("ctx") or {}).get("max_length")
            if isinstance(max_length, int):
                return f"Prompt must be {max_length:,} characters or fewer."
    return "Request validation failed."


def _safe_http_message(exc: StarletteHTTPException) -> str:
    if not isinstance(exc.detail, str):
        return "The request could not be completed."
    # Client errors and upstream provider failures should surface a useful message.
    if exc.status_code < 500 or exc.status_code in {502, 503, 504}:
        return exc.detail
    return "The request could not be completed."


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def _error_response(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, request_id=_request_id(request))
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())
