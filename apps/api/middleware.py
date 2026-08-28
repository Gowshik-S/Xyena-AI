from uuid import UUID, uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from packages.observability import bind_context


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        raw = request.headers.get("X-Correlation-ID")
        try:
            correlation_id = UUID(raw) if raw else uuid4()
        except ValueError:
            correlation_id = uuid4()
        request.state.correlation_id = correlation_id
        bind_context(correlation_id=str(correlation_id))
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = str(correlation_id)
        return response

