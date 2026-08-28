from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.audit import append_audit_event, enqueue_outbox
from packages.contracts.conversation import (
    ConversationCreateRequest,
    MessageCreateRequest,
    SessionCreateRequest,
)
from packages.contracts.identity import AuthenticatedPrincipal
from packages.persistence.models.agent import AgentRun, AgentRunEvent
from packages.persistence.models.conversation import Conversation, ConversationMember, Message, Session
from packages.persistence.models.ops import Job


class ConversationService:
    async def create_session(
        self,
        db: AsyncSession,
        principal: AuthenticatedPrincipal,
        request: SessionCreateRequest,
        correlation_id: UUID,
    ) -> Session:
        now = datetime.now(UTC)
        model = Session(
            id=uuid4(),
            tenant_id=principal.tenant_id,
            organization_id=principal.organization_id,
            user_id=principal.user_id,
            status="ACTIVE",
            last_seen_at=now,
            expires_at=request.expires_at,
            attributes=request.metadata,
        )
        db.add(model)
        await append_audit_event(
            db,
            tenant_id=principal.tenant_id,
            actor_type="USER",
            actor_id=str(principal.user_id),
            event_type="session.created",
            subject_type="session",
            subject_id=model.id,
            correlation_id=correlation_id,
        )
        await enqueue_outbox(
            db,
            tenant_id=principal.tenant_id,
            aggregate_type="session",
            aggregate_id=model.id,
            aggregate_version=1,
            event_type="session.created",
            correlation_id=correlation_id,
            payload={"session_id": str(model.id), "status": model.status},
        )
        return model

    async def get_session(
        self, db: AsyncSession, principal: AuthenticatedPrincipal, session_id: UUID
    ) -> Session:
        model = await db.scalar(
            select(Session).where(
                Session.id == session_id,
                Session.tenant_id == principal.tenant_id,
                Session.user_id == principal.user_id,
            )
        )
        if model is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return model

    async def close_session(
        self,
        db: AsyncSession,
        principal: AuthenticatedPrincipal,
        session_id: UUID,
        correlation_id: UUID,
    ) -> Session:
        model = await self.get_session(db, principal, session_id)
        model.status = "CLOSED"
        model.version += 1
        await append_audit_event(
            db,
            tenant_id=principal.tenant_id,
            actor_type="USER",
            actor_id=str(principal.user_id),
            event_type="session.closed",
            subject_type="session",
            subject_id=model.id,
            correlation_id=correlation_id,
        )
        return model

    async def create_conversation(
        self,
        db: AsyncSession,
        principal: AuthenticatedPrincipal,
        request: ConversationCreateRequest,
        correlation_id: UUID,
    ) -> Conversation:
        session = await self.get_session(db, principal, request.session_id)
        if session.status != "ACTIVE":
            raise HTTPException(status_code=409, detail="Session is not active")
        conversation = Conversation(
            id=uuid4(),
            tenant_id=principal.tenant_id,
            organization_id=principal.organization_id,
            user_id=principal.user_id,
            session_id=session.id,
            title=request.title,
            status="ACTIVE",
            model_policy_id=request.model_policy_id,
        )
        db.add(conversation)
        db.add(
            ConversationMember(
                id=uuid4(),
                tenant_id=principal.tenant_id,
                conversation_id=conversation.id,
                user_id=principal.user_id,
                member_role="OWNER",
            )
        )
        await append_audit_event(
            db,
            tenant_id=principal.tenant_id,
            actor_type="USER",
            actor_id=str(principal.user_id),
            event_type="conversation.created",
            subject_type="conversation",
            subject_id=conversation.id,
            correlation_id=correlation_id,
        )
        return conversation

    async def get_conversation(
        self, db: AsyncSession, principal: AuthenticatedPrincipal, conversation_id: UUID
    ) -> Conversation:
        conversation = await db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == principal.tenant_id,
                Conversation.user_id == principal.user_id,
            )
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation

    async def list_messages(
        self,
        db: AsyncSession,
        principal: AuthenticatedPrincipal,
        conversation_id: UUID,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> list[Message]:
        await self.get_conversation(db, principal, conversation_id)
        result = await db.scalars(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.tenant_id == principal.tenant_id,
                Message.sequence > after_sequence,
            )
            .order_by(Message.sequence.asc())
            .limit(limit)
        )
        return list(result)

    async def add_user_message_and_run(
        self,
        db: AsyncSession,
        principal: AuthenticatedPrincipal,
        conversation_id: UUID,
        request: MessageCreateRequest,
        correlation_id: UUID,
    ) -> tuple[Message, AgentRun]:
        conversation = await db.scalar(
            select(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == principal.tenant_id,
                Conversation.user_id == principal.user_id,
            )
            .with_for_update()
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        last_sequence = await db.scalar(
            select(func.coalesce(func.max(Message.sequence), 0))
            .where(Message.conversation_id == conversation_id)
        )
        message = Message(
            id=uuid4(),
            tenant_id=principal.tenant_id,
            conversation_id=conversation.id,
            sequence=int(last_sequence or 0) + 1,
            role="user",
            text_content=request.content,
            sensitivity="CONFIDENTIAL",
            attributes=request.metadata,
        )
        run = AgentRun(
            id=uuid4(),
            tenant_id=principal.tenant_id,
            organization_id=principal.organization_id,
            user_id=principal.user_id,
            session_id=conversation.session_id,
            conversation_id=conversation.id,
            case_id=request.case_id,
            correlation_id=correlation_id,
            start_agent="xyena-supervisor",
            status="QUEUED",
            input_message_id=message.id,
            usage={},
        )
        event = AgentRunEvent(
            id=uuid4(),
            tenant_id=principal.tenant_id,
            run_id=run.id,
            sequence=1,
            event_type="run.queued",
            status="QUEUED",
            data={"conversation_id": str(conversation.id)},
            occurred_at=datetime.now(UTC),
        )
        job = Job(
            id=uuid4(),
            tenant_id=principal.tenant_id,
            job_type="agent.run",
            payload={"run_id": str(run.id)},
            state="AVAILABLE",
            available_at=datetime.now(UTC),
            attempts=0,
            max_attempts=5,
        )
        db.add_all([message, run, event, job])
        conversation.version += 1
        await append_audit_event(
            db,
            tenant_id=principal.tenant_id,
            actor_type="USER",
            actor_id=str(principal.user_id),
            event_type="conversation.message.created",
            subject_type="message",
            subject_id=message.id,
            correlation_id=correlation_id,
            payload={"run_id": str(run.id), "conversation_id": str(conversation.id)},
        )
        await enqueue_outbox(
            db,
            tenant_id=principal.tenant_id,
            aggregate_type="agent_run",
            aggregate_id=run.id,
            aggregate_version=1,
            event_type="agent.run.queued",
            correlation_id=correlation_id,
            payload={"run_id": str(run.id)},
        )
        return message, run


conversation_service = ConversationService()
