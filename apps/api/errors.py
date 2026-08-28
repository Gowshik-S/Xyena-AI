from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_problem(request: Request, exc: HTTPException) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", uuid4())
        code = _code_for_status(exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            media_type="application/problem+json",
            content={
                "type": f"https://docs.xyena.ai/problems/{code.lower().replace('_', '-')}",
                "title": _title_for_status(exc.status_code),
                "status": exc.status_code,
                "detail": str(exc.detail),
                "instance": request.url.path,
                "code": code,
                "correlation_id": str(correlation_id),
                "errors": [],
            },
        )

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def validation_problem(
        request: Request, exc: RequestValidationError | ValidationError
    ) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", uuid4())
        return JSONResponse(
            status_code=422,
            media_type="application/problem+json",
            content={
                "type": "https://docs.xyena.ai/problems/validation-error",
                "title": "Validation error",
                "status": 422,
                "detail": "The request did not match the required schema.",
                "instance": request.url.path,
                "code": "VALIDATION_ERROR",
                "correlation_id": str(correlation_id),
                "errors": exc.errors(include_url=False, include_input=False),
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_problem(request: Request, exc: Exception) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", uuid4())
        return JSONResponse(
            status_code=500,
            media_type="application/problem+json",
            content={
                "type": "https://docs.xyena.ai/problems/internal-error",
                "title": "Internal server error",
                "status": 500,
                "detail": "The request could not be completed.",
                "instance": request.url.path,
                "code": "INTERNAL_ERROR",
                "correlation_id": str(correlation_id),
                "errors": [],
            },
        )


def _code_for_status(status_code: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "VERSION_CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
    }.get(status_code, "HTTP_ERROR")


def _title_for_status(status_code: int) -> str:
    return {
        400: "Bad request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not found",
        409: "Conflict",
        422: "Validation error",
        429: "Too many requests",
    }.get(status_code, "Request failed")
