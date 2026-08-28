from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import get_correlation_id, get_principal, get_scoped_session
from apps.api.services.conversation_service import conversation_service
from packages.contracts.common import CursorPage
from packages.contracts.conversation import (
    ConversationCreateRequest,
    ConversationView,
    MessageAccepted,
    MessageCreateRequest,
    MessageView,
)
from packages.contracts.identity import AuthenticatedPrincipal

router = APIRouter(prefix="/api/v1/conversations", tags=["Conversations"])


@router.post(
    "",
    operation_id="conversations_create",
    response_model=ConversationView,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    body: ConversationCreateRequest,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    correlation_id: UUID = Depends(get_correlation_id),
    db: AsyncSession = Depends(get_scoped_session),
) -> ConversationView:
    model = await conversation_service.create_conversation(db, principal, body, correlation_id)
    await db.flush()
    return ConversationView.model_validate(model)


@router.get(
    "/{conversation_id}",
    operation_id="conversations_get",
    response_model=ConversationView,
)
async def get_conversation(
    conversation_id: UUID,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    db: AsyncSession = Depends(get_scoped_session),
) -> ConversationView:
    model = await conversation_service.get_conversation(db, principal, conversation_id)
    return ConversationView.model_validate(model)


@router.get(
    "/{conversation_id}/messages",
    operation_id="conversation_messages_list",
    response_model=CursorPage[MessageView],
)
async def list_messages(
    conversation_id: UUID,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    principal: AuthenticatedPrincipal = Depends(get_principal),
    db: AsyncSession = Depends(get_scoped_session),
) -> CursorPage[MessageView]:
    messages = await conversation_service.list_messages(
        db,
        principal,
        conversation_id,
        after_sequence=after_sequence,
        limit=limit + 1,
    )
    has_more = len(messages) > limit
    selected = messages[:limit]
    next_cursor = str(selected[-1].sequence) if has_more and selected else None
    return CursorPage[MessageView](
        items=[_message_view(item) for item in selected],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.post(
    "/{conversation_id}/messages",
    operation_id="conversation_messages_create",
    response_model=MessageAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_message(
    conversation_id: UUID,
    body: MessageCreateRequest,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    correlation_id: UUID = Depends(get_correlation_id),
    db: AsyncSession = Depends(get_scoped_session),
) -> MessageAccepted:
    message, run = await conversation_service.add_user_message_and_run(
        db, principal, conversation_id, body, correlation_id
    )
    await db.flush()
    return MessageAccepted(message=_message_view(message), run_id=run.id)


def _message_view(message: object) -> MessageView:
    content = getattr(message, "structured_content") or getattr(message, "text_content") or ""
    return MessageView(
        id=getattr(message, "id"),
        conversation_id=getattr(message, "conversation_id"),
        sequence=getattr(message, "sequence"),
        role=getattr(message, "role"),
        content=content,
        sensitivity=getattr(message, "sensitivity"),
        created_at=getattr(message, "created_at"),
    )

