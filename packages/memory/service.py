from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.contracts.identity import AuthenticatedPrincipal
from packages.contracts.memory import MemoryCreateRequest, MemorySearchRequest
from packages.persistence.models.memory import MemoryRecord
from packages.persistence.models.ops import Job
from packages.config import get_settings


class MemoryService:
    async def create(
        self,
        db: AsyncSession,
        principal: AuthenticatedPrincipal,
        request: MemoryCreateRequest,
    ) -> MemoryRecord:
        if request.kind == "ORGANIZATION_FACT" and "organization-admin" not in principal.roles:
            raise PermissionError("Organization memory requires organization-admin.")
        user_id = None if request.kind == "ORGANIZATION_FACT" else principal.user_id
        record = MemoryRecord(
            id=uuid4(),
            tenant_id=principal.tenant_id,
            organization_id=principal.organization_id,
            user_id=user_id,
            kind=request.kind,
            content=request.content,
            structured_content=request.structured_content,
            sensitivity=request.sensitivity,
            source_type=request.source_type,
            source_id=request.source_id,
            confidence=1.0,
            status="ACTIVE",
            expires_at=request.expires_at,
        )
        db.add(record)
        if get_settings().openai_api_key is not None:
            db.add(
                Job(
                    id=uuid4(),
                    tenant_id=principal.tenant_id,
                    job_type="memory.embed",
                    payload={"memory_id": str(record.id)},
                    state="AVAILABLE",
                    available_at=datetime.now(UTC),
                    max_attempts=3,
                )
            )
        return record

    async def search(
        self,
        db: AsyncSession,
        principal: AuthenticatedPrincipal,
        request: MemorySearchRequest,
    ) -> list[MemoryRecord]:
        sensitivity_rank = {"PUBLIC": 0, "INTERNAL": 1, "CONFIDENTIAL": 2, "RESTRICTED": 3}
        maximum = sensitivity_rank.get(request.maximum_sensitivity, 2)
        allowed = [key for key, value in sensitivity_rank.items() if value <= maximum]
        query = select(MemoryRecord).where(
            MemoryRecord.tenant_id == principal.tenant_id,
            MemoryRecord.organization_id == principal.organization_id,
            or_(MemoryRecord.user_id == principal.user_id, MemoryRecord.user_id.is_(None)),
            MemoryRecord.status == "ACTIVE",
            or_(MemoryRecord.expires_at.is_(None), MemoryRecord.expires_at > datetime.now(UTC)),
            MemoryRecord.sensitivity.in_(allowed),
            MemoryRecord.content.ilike(f"%{request.query}%"),
        )
        if request.kinds:
            query = query.where(MemoryRecord.kind.in_(request.kinds))
        return list((await db.scalars(query.order_by(MemoryRecord.updated_at.desc()).limit(request.limit))).all())

    async def get(
        self, db: AsyncSession, principal: AuthenticatedPrincipal, memory_id: UUID
    ) -> MemoryRecord:
        record = await db.scalar(
            select(MemoryRecord).where(
                MemoryRecord.id == memory_id,
                MemoryRecord.tenant_id == principal.tenant_id,
                MemoryRecord.organization_id == principal.organization_id,
                or_(MemoryRecord.user_id == principal.user_id, MemoryRecord.user_id.is_(None)),
            )
        )
        if record is None:
            raise LookupError("Memory record not found.")
        return record

    async def forget(
        self, db: AsyncSession, principal: AuthenticatedPrincipal, memory_id: UUID
    ) -> None:
        record = await self.get(db, principal, memory_id)
        if record.user_id is None and "organization-admin" not in principal.roles:
            raise PermissionError("Organization memory requires organization-admin.")
        record.status = "FORGOTTEN"
        record.content = "[forgotten]"
        record.structured_content = {}
        record.embedding = None
        record.version += 1


memory_service = MemoryService()
