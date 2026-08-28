from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import get_correlation_id, get_principal, get_scoped_session
from apps.api.services.conversation_service import conversation_service
from packages.contracts.conversation import SessionCreateRequest, SessionView
from packages.contracts.identity import AuthenticatedPrincipal

router = APIRouter(prefix="/api/v1/sessions", tags=["Sessions"])


@router.post(
    "",
    operation_id="sessions_create",
    response_model=SessionView,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    body: SessionCreateRequest,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    correlation_id: UUID = Depends(get_correlation_id),
    db: AsyncSession = Depends(get_scoped_session),
) -> SessionView:
    model = await conversation_service.create_session(db, principal, body, correlation_id)
    await db.flush()
    return SessionView.model_validate(model)


@router.get(
    "/{session_id}", operation_id="sessions_get", response_model=SessionView
)
async def get_session(
    session_id: UUID,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    db: AsyncSession = Depends(get_scoped_session),
) -> SessionView:
    return SessionView.model_validate(await conversation_service.get_session(db, principal, session_id))


@router.delete(
    "/{session_id}",
    operation_id="sessions_close",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def close_session(
    session_id: UUID,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    correlation_id: UUID = Depends(get_correlation_id),
    db: AsyncSession = Depends(get_scoped_session),
) -> Response:
    await conversation_service.close_session(db, principal, session_id, correlation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

