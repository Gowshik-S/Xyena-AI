from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.contracts.data import DataGrantCreateRequest, DataObjectRegisterRequest, DataUploadRequest
from packages.contracts.identity import AuthenticatedPrincipal
from packages.persistence.models.data import DataAccessEvent, DataGrant, DataObject

from .object_store import ObjectStore, UploadTicket


class DataVaultService:
    def __init__(self, object_store: ObjectStore | None = None) -> None:
        self.object_store = object_store or ObjectStore()

    async def initiate_upload(
        self,
        db: AsyncSession,
        principal: AuthenticatedPrincipal,
        request: DataUploadRequest,
        correlation_id: UUID,
    ) -> tuple[DataObject, UploadTicket]:
        object_id = uuid4()
        safe_name = "".join(
            character if character.isalnum() or character in ("-", "_", ".") else "_"
            for character in request.display_name
        )[:200]
        object_key = f"{principal.tenant_id}/{principal.user_id}/{object_id}/{safe_name}"
        value = DataObject(
            id=object_id,
            tenant_id=principal.tenant_id,
            organization_id=principal.organization_id,
            owner_user_id=principal.user_id,
            object_key=object_key,
            display_name=request.display_name,
            media_type=request.media_type,
            size_bytes=request.size_bytes,
            content_hash=request.content_hash.lower(),
            classification=request.classification,
            schema_name=request.schema_name,
            attributes=request.metadata,
            status="PENDING_UPLOAD",
        )
        ticket = await self.object_store.presign_upload(
            key=object_key,
            media_type=request.media_type,
            content_hash=request.content_hash,
        )
        db.add(value)
        self._access_event(db, principal, value.id, "UPLOAD_INITIATED", correlation_id)
        return value, ticket

    async def complete_upload(
        self,
        db: AsyncSession,
        principal: AuthenticatedPrincipal,
        object_id: UUID,
        correlation_id: UUID,
    ) -> DataObject:
        value = await self._get_owned(db, principal, object_id, allowed_statuses=("PENDING_UPLOAD",))
        await self.object_store.verify_upload(
            key=value.object_key,
            size_bytes=value.size_bytes,
            content_hash=value.content_hash,
        )
        value.status = "ACTIVE"
        value.version += 1
        self._access_event(db, principal, value.id, "UPLOAD_COMPLETED", correlation_id)
        return value

    async def download_ticket(
        self,
        db: AsyncSession,
        principal: AuthenticatedPrincipal,
        object_id: UUID,
        correlation_id: UUID,
    ) -> str:
        value = await self.get(db, principal, object_id)
        url = await self.object_store.presign_download(key=value.object_key)
        self._access_event(db, principal, value.id, "DOWNLOAD_AUTHORIZED", correlation_id)
        return url

    async def register(
        self,
        db: AsyncSession,
        principal: AuthenticatedPrincipal,
        request: DataObjectRegisterRequest,
        correlation_id: UUID,
    ) -> DataObject:
        required_prefix = f"{principal.tenant_id}/{principal.user_id}/"
        if not request.object_key.startswith(required_prefix):
            raise PermissionError("Object key must be inside the authenticated tenant/user prefix.")
        existing = await db.scalar(
            select(DataObject).where(
                DataObject.tenant_id == principal.tenant_id,
                DataObject.object_key == request.object_key,
            )
        )
        if existing is not None:
            raise ValueError("Object key is already registered.")
        value = DataObject(
            id=uuid4(),
            tenant_id=principal.tenant_id,
            organization_id=principal.organization_id,
            owner_user_id=principal.user_id,
            object_key=request.object_key,
            display_name=request.display_name,
            media_type=request.media_type,
            size_bytes=request.size_bytes,
            content_hash=request.content_hash.lower(),
            classification=request.classification,
            schema_name=request.schema_name,
            attributes=request.metadata,
            status="ACTIVE",
        )
        db.add(value)
        db.add(
            DataAccessEvent(
                id=uuid4(),
                tenant_id=principal.tenant_id,
                data_object_id=value.id,
                actor_type="USER",
                actor_id=str(principal.user_id),
                purpose="object registration",
                action="REGISTER",
                correlation_id=correlation_id,
                outcome="SUCCEEDED",
            )
        )
        return value

    async def list(self, db: AsyncSession, principal: AuthenticatedPrincipal) -> list[DataObject]:
        return list(
            (
                await db.scalars(
                    select(DataObject)
                    .where(
                        DataObject.tenant_id == principal.tenant_id,
                        DataObject.organization_id == principal.organization_id,
                        DataObject.owner_user_id == principal.user_id,
                        DataObject.status == "ACTIVE",
                    )
                    .order_by(DataObject.created_at.desc())
                )
            ).all()
        )

    async def get(
        self, db: AsyncSession, principal: AuthenticatedPrincipal, object_id: UUID
    ) -> DataObject:
        value = await db.scalar(
            select(DataObject).where(
                DataObject.id == object_id,
                DataObject.tenant_id == principal.tenant_id,
                DataObject.organization_id == principal.organization_id,
                DataObject.owner_user_id == principal.user_id,
                DataObject.status == "ACTIVE",
            )
        )
        if value is None:
            raise LookupError("Data object not found.")
        return value

    async def _get_owned(
        self,
        db: AsyncSession,
        principal: AuthenticatedPrincipal,
        object_id: UUID,
        *,
        allowed_statuses: tuple[str, ...],
    ) -> DataObject:
        value = await db.scalar(
            select(DataObject).where(
                DataObject.id == object_id,
                DataObject.tenant_id == principal.tenant_id,
                DataObject.organization_id == principal.organization_id,
                DataObject.owner_user_id == principal.user_id,
                DataObject.status.in_(allowed_statuses),
            )
        )
        if value is None:
            raise LookupError("Data object not found.")
        return value

    async def create_grant(
        self,
        db: AsyncSession,
        principal: AuthenticatedPrincipal,
        object_id: UUID,
        request: DataGrantCreateRequest,
    ) -> DataGrant:
        await self.get(db, principal, object_id)
        value = DataGrant(
            id=uuid4(),
            tenant_id=principal.tenant_id,
            data_object_id=object_id,
            grantor_user_id=principal.user_id,
            grantee_type=request.grantee_type,
            grantee_id=request.grantee_id,
            purposes=request.purposes,
            permissions=request.permissions,
            status="ACTIVE",
            expires_at=request.expires_at,
        )
        db.add(value)
        return value

    async def delete(
        self,
        db: AsyncSession,
        principal: AuthenticatedPrincipal,
        object_id: UUID,
        correlation_id: UUID,
    ) -> None:
        value = await self.get(db, principal, object_id)
        await self.object_store.delete(key=value.object_key)
        value.status = "DELETED"
        value.deleted_at = datetime.now(UTC)
        value.version += 1
        db.add(
            DataAccessEvent(
                id=uuid4(),
                tenant_id=principal.tenant_id,
                data_object_id=value.id,
                actor_type="USER",
                actor_id=str(principal.user_id),
                purpose="user deletion request",
                action="DELETE",
                correlation_id=correlation_id,
                outcome="SUCCEEDED",
            )
        )

    @staticmethod
    def _access_event(
        db: AsyncSession,
        principal: AuthenticatedPrincipal,
        object_id: UUID,
        action: str,
        correlation_id: UUID,
    ) -> None:
        db.add(
            DataAccessEvent(
                id=uuid4(),
                tenant_id=principal.tenant_id,
                data_object_id=object_id,
                actor_type="USER",
                actor_id=str(principal.user_id),
                purpose="user data management",
                action=action,
                correlation_id=correlation_id,
                outcome="SUCCEEDED",
            )
        )


data_vault_service = DataVaultService()
