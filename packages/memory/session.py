from typing import Any
from uuid import UUID, uuid4

from agents import RunContextWrapper, SessionSettings
from agents.items import TResponseInputItem
from sqlalchemy import func, select, text

from packages.persistence import get_database
from packages.persistence.models.memory import SessionItem


class PostgresAgentSession:
    """Tenant-scoped Agents SDK Session implementation backed by PostgreSQL."""

    session_settings: SessionSettings | None = None

    def __init__(self, tenant_id: UUID, session_id: UUID, conversation_id: UUID) -> None:
        self.tenant_id = tenant_id
        self.session_id = str(session_id)
        self._session_uuid = session_id
        self.conversation_id = conversation_id

    async def get_items(
        self,
        limit: int | None = None,
        *,
        wrapper: RunContextWrapper[Any] | None = None,
    ) -> list[TResponseInputItem]:
        async with get_database().session(tenant_id=self.tenant_id, service_role="worker") as db:
            query = select(SessionItem).where(
                SessionItem.tenant_id == self.tenant_id,
                SessionItem.session_id == self._session_uuid,
                SessionItem.conversation_id == self.conversation_id,
            )
            if limit is not None:
                query = query.order_by(SessionItem.sequence.desc()).limit(max(0, limit))
                values = list(reversed((await db.scalars(query)).all()))
            else:
                values = list((await db.scalars(query.order_by(SessionItem.sequence))).all())
            return [value.item for value in values]  # type: ignore[return-value]

    async def add_items(
        self,
        items: list[TResponseInputItem],
        *,
        wrapper: RunContextWrapper[Any] | None = None,
    ) -> None:
        async with get_database().session(tenant_id=self.tenant_id, service_role="worker") as db:
            await db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
                {"scope": f"{self.tenant_id}:{self._session_uuid}"},
            )
            last = await db.scalar(
                select(func.max(SessionItem.sequence)).where(
                    SessionItem.tenant_id == self.tenant_id,
                    SessionItem.session_id == self._session_uuid,
                )
            )
            sequence = int(last or 0)
            for item in items:
                sequence += 1
                db.add(
                    SessionItem(
                        id=uuid4(),
                        tenant_id=self.tenant_id,
                        session_id=self._session_uuid,
                        conversation_id=self.conversation_id,
                        sequence=sequence,
                        item=dict(item),
                    )
                )

    async def pop_item(
        self, *, wrapper: RunContextWrapper[Any] | None = None
    ) -> TResponseInputItem | None:
        async with get_database().session(tenant_id=self.tenant_id, service_role="worker") as db:
            value = await db.scalar(
                select(SessionItem)
                .where(
                    SessionItem.tenant_id == self.tenant_id,
                    SessionItem.session_id == self._session_uuid,
                    SessionItem.conversation_id == self.conversation_id,
                )
                .order_by(SessionItem.sequence.desc())
                .limit(1)
                .with_for_update()
            )
            if value is None:
                return None
            result = value.item
            await db.delete(value)
            return result  # type: ignore[return-value]

    async def clear_session(
        self, *, wrapper: RunContextWrapper[Any] | None = None
    ) -> None:
        async with get_database().session(tenant_id=self.tenant_id, service_role="worker") as db:
            values = (
                await db.scalars(
                    select(SessionItem).where(
                        SessionItem.tenant_id == self.tenant_id,
                        SessionItem.session_id == self._session_uuid,
                        SessionItem.conversation_id == self.conversation_id,
                    )
                )
            ).all()
            for value in values:
                await db.delete(value)
