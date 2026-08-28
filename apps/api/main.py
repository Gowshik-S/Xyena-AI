from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.errors import register_error_handlers
from apps.api.middleware import CorrelationMiddleware
from apps.api.routes import approvals, conversations, data, health, memory, runs, sessions
from packages.config import get_settings
from packages.observability import configure_logging, configure_telemetry
from packages.persistence import get_database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    yield
    await get_database().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Xyena Core API",
        summary="Xyena multi-agent and Guardian platform API",
        description=(
            "Authenticated, tenant-isolated sessions, conversations, agent runs, approvals, "
            "memory, and data controls for the Xyena platform."
        ),
        version="0.1.0",
        openapi_version="3.1.0",
        openapi_url="/openapi.json" if settings.env != "production" else None,
        docs_url="/docs" if settings.env != "production" else None,
        redoc_url="/redoc" if settings.env != "production" else None,
        lifespan=lifespan,
    )
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Correlation-ID", "Idempotency-Key", "If-Match"],
        expose_headers=["X-Correlation-ID", "ETag", "Retry-After"],
    )
    app.include_router(health.router)
    app.include_router(sessions.router)
    app.include_router(conversations.router)
    app.include_router(runs.router)
    app.include_router(approvals.router)
    app.include_router(memory.router)
    app.include_router(data.router)
    register_error_handlers(app)
    configure_telemetry(app, "xyena-api")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("apps.api.main:app", host=settings.api_host, port=settings.api_port, reload=False)
