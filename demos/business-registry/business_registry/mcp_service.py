import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select

from .database import session
from .domain import canonical_hash, iso
from .mcp_security import RuntimeScope
from .models import Business
from .service import registry_service
from .settings import get_settings


class RegistryMcpService:
    async def business_get(self, scope: RuntimeScope, identifier: str) -> dict[str, Any]:
        async with session() as db:
            data = await registry_service.get_business(db, scope.tenant_id, identifier)
            return self._wrap(
                scope, "registry.business.v1", data, data["version"], data["updated_at"]
            )

    async def business_verify(
        self,
        scope: RuntimeScope,
        *,
        identifier: str,
        claimed_legal_name: str | None,
        claimed_gstin: str | None,
        claimed_status: str | None,
    ) -> dict[str, Any]:
        source = await self.business_get(scope, identifier)
        business = source["data"]
        comparisons: dict[str, dict[str, Any]] = {}
        if claimed_legal_name is not None:
            comparisons["legal_name"] = {
                "claimed": claimed_legal_name,
                "source": business["legal_name"],
                "match": claimed_legal_name.casefold() == business["legal_name"].casefold(),
            }
        if claimed_gstin is not None:
            comparisons["primary_gstin"] = {
                "claimed": claimed_gstin.upper(), "source": business["primary_gstin"],
                "match": claimed_gstin.upper() == business["primary_gstin"],
            }
        if claimed_status is not None:
            comparisons["status"] = {
                "claimed": claimed_status.upper(), "source": business["status"],
                "match": claimed_status.upper() == business["status"],
            }
        source["schema_version"] = "registry.business-verification.v1"
        source["data"] = {
            "business_id": business["business_id"],
            "verified": bool(comparisons) and all(value["match"] for value in comparisons.values()),
            "legally_active": business["status"] == "ACTIVE",
            "comparisons": comparisons,
            "risk_flags": business["risk_flags"],
            "source_record": business,
        }
        return source

    async def business_search(
        self,
        scope: RuntimeScope,
        *,
        query: str,
        status: str | None,
        limit: int,
    ) -> dict[str, Any]:
        async with session() as db:
            statement = select(Business).where(Business.tenant_id == scope.tenant_id)
            if query.strip():
                term = f"%{query.strip()}%"
                statement = statement.where(
                    or_(
                        Business.registry_number.ilike(term), Business.business_id.ilike(term),
                        Business.legal_name.ilike(term), Business.trade_name.ilike(term),
                        Business.primary_gstin.ilike(term),
                    )
                )
            if status:
                statement = statement.where(Business.status == status.upper())
            values = (
                await db.scalars(
                    statement.order_by(Business.legal_name).limit(max(1, min(limit, 50)))
                )
            ).all()
            updated = max((value.updated_at for value in values), default=datetime.now(UTC))
            version = max((value.version for value in values), default=1)
            return self._wrap(
                scope, "registry.business-search.v1",
                {"items": [registry_service.business_summary(value) for value in values]},
                version, updated,
            )

    async def ownership_get(self, scope: RuntimeScope, business_id: str) -> dict[str, Any]:
        async with session() as db:
            business = await registry_service._business(db, scope.tenant_id, business_id)
            data = await registry_service.ownership(db, scope.tenant_id, business.id)
            return self._wrap(
                scope, "registry.ownership.v1",
                {"business": registry_service.business_summary(business), "owners": data},
                max([business.version, *[item["version"] for item in data]]), business.updated_at,
            )

    async def relationships_get(self, scope: RuntimeScope, business_id: str) -> dict[str, Any]:
        async with session() as db:
            business = await registry_service._business(db, scope.tenant_id, business_id)
            data = await registry_service.relationships(db, scope.tenant_id, business.id)
            return self._wrap(
                scope, "registry.relationships.v1",
                {"business": registry_service.business_summary(business), "relationships": data},
                max([business.version, *[item["version"] for item in data]]), business.updated_at,
            )

    async def authorized_persons_get(
        self, scope: RuntimeScope, business_id: str
    ) -> dict[str, Any]:
        async with session() as db:
            business = await registry_service._business(db, scope.tenant_id, business_id)
            data = await registry_service.authorized_persons(db, scope.tenant_id, business.id)
            return self._wrap(
                scope, "registry.authorized-persons.v1",
                {"business": registry_service.business_summary(business), "authorized_persons": data},
                max([business.version, *[item["version"] for item in data]]), business.updated_at,
            )

    @staticmethod
    def _wrap(
        scope: RuntimeScope,
        schema_version: str,
        data: dict[str, Any],
        record_version: int,
        updated_at: datetime | str | None,
    ) -> dict[str, Any]:
        retrieved = datetime.now(UTC)
        updated_value = updated_at if isinstance(updated_at, str) else iso(updated_at)
        body = {
            "schema_version": schema_version,
            "source_system": "xyena-demo-business-registry",
            "request_id": scope.call_id,
            "record_version": record_version,
            "updated_at": updated_value,
            "retrieved_at": retrieved.isoformat(),
            "fresh_until": (retrieved + timedelta(minutes=10)).isoformat(),
            "data": data,
            "security_labels": ["EXTERNAL_DATA", "SYNTHETIC_DEMO_SOURCE", "BUSINESS_IDENTITY"],
        }
        signature = hmac.new(
            get_settings().mcp_token.get_secret_value().encode(),
            json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode(),
            hashlib.sha256,
        ).hexdigest()
        body["source_signature"] = signature
        body["source_hash"] = canonical_hash(data)
        return body


registry_mcp_service = RegistryMcpService()
