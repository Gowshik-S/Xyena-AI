from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from .auth import BrowserScope, require_roles
from .domain import canonical_hash, iso, record_change
from .models import (
    AuditEvent,
    Business,
    BusinessAddress,
    BusinessName,
    BusinessPerson,
    BusinessRelationship,
    ChangeRequest,
    OwnershipLink,
)
from .schemas import BusinessCreate, ChangeRequestCreate, StatusTransition


class RegistryDomainError(RuntimeError):
    pass


class RegistryNotFoundError(RegistryDomainError):
    pass


class RegistryConflictError(RegistryDomainError):
    pass


class RegistryService:
    async def session_view(self, scope: BrowserScope) -> dict[str, Any]:
        return {
            "user": {"id": scope.user.id, "display_name": scope.user.display_name, "email": scope.user.email},
            "tenant_id": scope.tenant_id,
            "roles": sorted(scope.roles),
            "environment": "SYNTHETIC_NON_PRODUCTION",
        }

    async def dashboard(self, db: AsyncSession, scope: BrowserScope) -> dict[str, Any]:
        status_rows = (
            await db.execute(
                select(Business.status, func.count(Business.id))
                .where(Business.tenant_id == scope.tenant_id)
                .group_by(Business.status)
            )
        ).all()
        type_rows = (
            await db.execute(
                select(Business.business_type, func.count(Business.id))
                .where(Business.tenant_id == scope.tenant_id)
                .group_by(Business.business_type)
            )
        ).all()
        pending_changes = await db.scalar(
            select(func.count(ChangeRequest.id)).where(
                ChangeRequest.tenant_id == scope.tenant_id,
                ChangeRequest.status == "SUBMITTED",
            )
        )
        recent = (
            await db.scalars(
                select(Business)
                .where(Business.tenant_id == scope.tenant_id)
                .order_by(Business.updated_at.desc())
                .limit(6)
            )
        ).all()
        risk_flag_sets = (
            await db.scalars(
                select(Business.risk_flags).where(Business.tenant_id == scope.tenant_id)
            )
        ).all()
        flagged = sum(1 for flags in risk_flag_sets if flags)
        return {
            "status_counts": dict(status_rows),
            "type_counts": dict(type_rows),
            "pending_changes": pending_changes or 0,
            "flagged_businesses": flagged,
            "recent_businesses": [self.business_summary(value) for value in recent],
        }

    async def list_businesses(
        self,
        db: AsyncSession,
        scope: BrowserScope,
        *,
        query: str | None = None,
        status: str | None = None,
        business_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        statement = select(Business).where(Business.tenant_id == scope.tenant_id)
        if query:
            term = f"%{query.strip()}%"
            statement = statement.where(
                or_(
                    Business.registry_number.ilike(term),
                    Business.business_id.ilike(term),
                    Business.legal_name.ilike(term),
                    Business.trade_name.ilike(term),
                    Business.primary_gstin.ilike(term),
                )
            )
        if status:
            statement = statement.where(Business.status == status.upper())
        if business_type:
            statement = statement.where(Business.business_type == business_type.upper())
        values = (
            await db.scalars(statement.order_by(Business.legal_name).limit(max(1, min(limit, 100))))
        ).all()
        return [self.business_summary(value) for value in values]

    async def get_business(
        self, db: AsyncSession, tenant_id: str, business_id: str
    ) -> dict[str, Any]:
        business = await self._business(db, tenant_id, business_id)
        names = (
            await db.scalars(
                select(BusinessName).where(
                    BusinessName.tenant_id == tenant_id,
                    BusinessName.business_id == business.id,
                ).order_by(BusinessName.effective_from.desc())
            )
        ).all()
        addresses = (
            await db.scalars(
                select(BusinessAddress).where(
                    BusinessAddress.tenant_id == tenant_id,
                    BusinessAddress.business_id == business.id,
                ).order_by(BusinessAddress.effective_from.desc())
            )
        ).all()
        people = (
            await db.scalars(
                select(BusinessPerson).where(
                    BusinessPerson.tenant_id == tenant_id,
                    BusinessPerson.business_id == business.id,
                ).order_by(BusinessPerson.display_name)
            )
        ).all()
        ownership = await self.ownership(db, tenant_id, business.id)
        relationships = await self.relationships(db, tenant_id, business.id)
        changes = (
            await db.scalars(
                select(ChangeRequest).where(
                    ChangeRequest.tenant_id == tenant_id,
                    ChangeRequest.business_id == business.id,
                ).order_by(ChangeRequest.created_at.desc())
            )
        ).all()
        result = self.business_projection(business)
        result.update(
            {
                "names": [self.name_projection(value) for value in names],
                "addresses": [self.address_projection(value) for value in addresses],
                "authorized_persons": [self.person_projection(value) for value in people],
                "ownership": ownership,
                "relationships": relationships,
                "change_requests": [self.change_projection(value) for value in changes],
            }
        )
        return result

    async def create_business(
        self, db: AsyncSession, scope: BrowserScope, request: BusinessCreate
    ) -> dict[str, Any]:
        require_roles(scope, "REGISTRY_OPERATOR")
        if request.incorporation_date > date.today():
            raise RegistryDomainError("Incorporation date cannot be in the future.")
        exists = await db.scalar(
            select(Business.id).where(
                Business.tenant_id == scope.tenant_id,
                or_(
                    Business.registry_number == request.registry_number,
                    Business.business_id == request.business_id,
                ),
            )
        )
        if exists:
            raise RegistryConflictError("The registry number or business ID already exists.")
        address = {
            "line1": request.address_line1,
            "city": request.city,
            "state_code": request.registered_state_code,
            "postal_code": request.postal_code,
            "country": "IN",
        }
        source = request.model_dump(mode="json")
        business = Business(
            id=str(uuid4()), tenant_id=scope.tenant_id, business_id=request.business_id,
            registry_number=request.registry_number, business_type=request.business_type,
            legal_name=request.legal_name, trade_name=request.trade_name,
            incorporation_date=request.incorporation_date, status="PENDING_REVIEW",
            registered_state_code=request.registered_state_code, registered_address=address,
            industry_code=request.industry_code, msme_classification=request.msme_classification,
            primary_gstin=request.primary_gstin, pan_token=f"pan_demo_{uuid4().hex[:10]}",
            risk_flags=["PENDING_IDENTITY_REVIEW"], source_hash=canonical_hash(source), version=1,
            created_by=scope.user.id, updated_by=scope.user.id,
        )
        db.add(business)
        await db.flush()
        db.add_all([
            BusinessName(
                id=str(uuid4()), tenant_id=scope.tenant_id, business_id=business.id,
                name_type="LEGAL", name=business.legal_name,
                effective_from=business.incorporation_date, source_hash=canonical_hash(business.legal_name),
                record_version=1,
            ),
            BusinessAddress(
                id=str(uuid4()), tenant_id=scope.tenant_id, business_id=business.id,
                address_type="REGISTERED", address_json=address, verification_status="PENDING",
                effective_from=business.incorporation_date, source_hash=canonical_hash(address),
                record_version=1,
            ),
        ])
        record_change(
            db, tenant_id=scope.tenant_id, aggregate_type="BUSINESS", aggregate_id=business.id,
            aggregate_version=1, event_type="business.created", actor_type="USER",
            actor_id=scope.user.id, reason="New synthetic business submitted for review",
        )
        return self.business_projection(business)

    async def transition_status(
        self,
        db: AsyncSession,
        scope: BrowserScope,
        business_id: str,
        request: StatusTransition,
        expected_version: int,
    ) -> dict[str, Any]:
        require_roles(scope, "REGISTRY_REVIEWER")
        business = await self._business(db, scope.tenant_id, business_id, lock=True)
        if business.version != expected_version:
            raise RegistryConflictError("The business record changed. Reload it before review.")
        allowed = {
            "PENDING_REVIEW": {"ACTIVE", "REJECTED"},
            "ACTIVE": {"SUSPENDED", "DISSOLVED"},
            "SUSPENDED": {"ACTIVE", "DISSOLVED"},
        }
        if request.target_status not in allowed.get(business.status, set()):
            raise RegistryConflictError(
                f"A {business.status} record cannot move to {request.target_status}."
            )
        prior = business.status
        business.status = request.target_status
        business.version += 1
        business.updated_by = scope.user.id
        business.risk_flags = [flag for flag in business.risk_flags if flag != "PENDING_IDENTITY_REVIEW"]
        if request.target_status in {"SUSPENDED", "DISSOLVED", "REJECTED"}:
            business.risk_flags = sorted(set([*business.risk_flags, f"REGISTRY_{request.target_status}"]))
        business.source_hash = self._identity_hash(business)
        event_name = "business.activated" if request.target_status == "ACTIVE" else f"business.{request.target_status.lower()}"
        record_change(
            db, tenant_id=scope.tenant_id, aggregate_type="BUSINESS", aggregate_id=business.id,
            aggregate_version=business.version, event_type=event_name,
            actor_type="USER", actor_id=scope.user.id, reason=request.reason,
            metadata={"prior_status": prior, "new_status": request.target_status},
        )
        return self.business_projection(business)

    async def create_change_request(
        self,
        db: AsyncSession,
        scope: BrowserScope,
        business_id: str,
        request: ChangeRequestCreate,
    ) -> dict[str, Any]:
        require_roles(scope, "REGISTRY_OPERATOR")
        business = await self._business(db, scope.tenant_id, business_id)
        if business.status not in {"ACTIVE", "SUSPENDED"}:
            raise RegistryConflictError("Changes can only be proposed for active or suspended records.")
        if request.target_version != business.version:
            raise RegistryConflictError("The target business version is stale.")
        patch = request.model_dump(
            exclude={"target_version", "reason"}, exclude_none=True, mode="json"
        )
        if not patch:
            raise RegistryDomainError("At least one identity field must be proposed.")
        if "registered_address" in patch:
            required = {"line1", "city", "state_code", "postal_code", "country"}
            if required - set(patch["registered_address"]):
                raise RegistryDomainError("The proposed registered address is incomplete.")
        value = ChangeRequest(
            id=str(uuid4()), tenant_id=scope.tenant_id, business_id=business.id,
            target_version=business.version, requested_patch=patch, reason=request.reason,
            status="SUBMITTED", requested_by=scope.user.id,
        )
        db.add(value)
        record_change(
            db, tenant_id=scope.tenant_id, aggregate_type="CHANGE_REQUEST", aggregate_id=value.id,
            aggregate_version=1, event_type="business.change_submitted", actor_type="USER",
            actor_id=scope.user.id, reason=request.reason, metadata={"business_id": business.id},
        )
        return self.change_projection(value)

    async def list_changes(
        self, db: AsyncSession, scope: BrowserScope, status: str | None = None
    ) -> list[dict[str, Any]]:
        statement = (
            select(ChangeRequest, Business)
            .join(Business, Business.id == ChangeRequest.business_id)
            .where(ChangeRequest.tenant_id == scope.tenant_id)
        )
        if status:
            statement = statement.where(ChangeRequest.status == status.upper())
        rows = (await db.execute(statement.order_by(ChangeRequest.created_at.desc()))).all()
        return [
            {**self.change_projection(change), "business": self.business_summary(business)}
            for change, business in rows
        ]

    async def decide_change(
        self,
        db: AsyncSession,
        scope: BrowserScope,
        change_id: str,
        *,
        approve: bool,
        decision_reason: str,
    ) -> dict[str, Any]:
        require_roles(scope, "REGISTRY_REVIEWER")
        change = await db.scalar(
            select(ChangeRequest)
            .where(ChangeRequest.id == change_id, ChangeRequest.tenant_id == scope.tenant_id)
            .with_for_update()
        )
        if change is None:
            raise RegistryNotFoundError("Change request was not found.")
        if change.status != "SUBMITTED":
            raise RegistryConflictError("Only a submitted change request can be decided.")
        business = await self._business(db, scope.tenant_id, change.business_id, lock=True)
        if approve and business.version != change.target_version:
            raise RegistryConflictError("The business changed after this request was submitted.")
        change.status = "APPROVED" if approve else "REJECTED"
        change.reviewed_by = scope.user.id
        change.decision_reason = decision_reason
        change.decided_at = datetime.now(UTC)
        if approve:
            prior_name = business.legal_name
            patch = change.requested_patch
            if "primary_gstin" in patch:
                duplicate = await db.scalar(
                    select(Business.id).where(
                        Business.tenant_id == scope.tenant_id,
                        Business.primary_gstin == patch["primary_gstin"],
                        Business.id != business.id,
                    )
                )
                if duplicate:
                    raise RegistryConflictError("The proposed GSTIN belongs to another business record.")
            for field in (
                "legal_name", "trade_name", "industry_code", "msme_classification", "primary_gstin"
            ):
                if field in patch:
                    setattr(business, field, patch[field])
            if "registered_address" in patch:
                business.registered_address = patch["registered_address"]
                business.registered_state_code = patch["registered_address"]["state_code"]
            business.version += 1
            business.updated_by = scope.user.id
            business.source_hash = self._identity_hash(business)
            change.applied_version = business.version
            if business.legal_name != prior_name:
                db.add(BusinessName(
                    id=str(uuid4()), tenant_id=scope.tenant_id, business_id=business.id,
                    name_type="LEGAL", name=business.legal_name, effective_from=date.today(),
                    source_hash=canonical_hash(business.legal_name), record_version=business.version,
                ))
            if "registered_address" in patch:
                db.add(BusinessAddress(
                    id=str(uuid4()), tenant_id=scope.tenant_id, business_id=business.id,
                    address_type="REGISTERED", address_json=business.registered_address,
                    verification_status="VERIFIED", effective_from=date.today(),
                    source_hash=canonical_hash(business.registered_address), record_version=business.version,
                ))
        record_change(
            db, tenant_id=scope.tenant_id, aggregate_type="BUSINESS", aggregate_id=business.id,
            aggregate_version=business.version,
            event_type="business.updated" if approve else "business.change_rejected",
            actor_type="USER", actor_id=scope.user.id, reason=decision_reason,
            metadata={"change_request_id": change.id},
        )
        return self.change_projection(change)

    async def ownership(
        self, db: AsyncSession, tenant_id: str, business_id: str
    ) -> list[dict[str, Any]]:
        values = (
            await db.scalars(
                select(OwnershipLink).where(
                    OwnershipLink.tenant_id == tenant_id,
                    OwnershipLink.business_id == business_id,
                ).order_by(OwnershipLink.ownership_percentage.desc())
            )
        ).all()
        return [self.ownership_projection(value) for value in values]

    async def relationships(
        self, db: AsyncSession, tenant_id: str, business_id: str
    ) -> list[dict[str, Any]]:
        source = aliased(Business)
        target = aliased(Business)
        rows = (
            await db.execute(
                select(BusinessRelationship, source, target)
                .join(source, source.id == BusinessRelationship.source_business_id)
                .join(target, target.id == BusinessRelationship.target_business_id)
                .where(
                    BusinessRelationship.tenant_id == tenant_id,
                    or_(
                        BusinessRelationship.source_business_id == business_id,
                        BusinessRelationship.target_business_id == business_id,
                    ),
                )
                .order_by(source.legal_name, target.legal_name)
            )
        ).all()
        return [
            {
                **self.relationship_projection(value),
                "source_business": self.business_summary(source_business),
                "target_business": self.business_summary(target_business),
            }
            for value, source_business, target_business in rows
        ]

    async def all_relationships(
        self, db: AsyncSession, scope: BrowserScope
    ) -> list[dict[str, Any]]:
        source = aliased(Business)
        target = aliased(Business)
        rows = (
            await db.execute(
                select(BusinessRelationship, source, target)
                .join(source, source.id == BusinessRelationship.source_business_id)
                .join(target, target.id == BusinessRelationship.target_business_id)
                .where(BusinessRelationship.tenant_id == scope.tenant_id)
                .order_by(source.legal_name, target.legal_name)
            )
        ).all()
        return [
            {
                **self.relationship_projection(value),
                "source_business": self.business_summary(source_business),
                "target_business": self.business_summary(target_business),
            }
            for value, source_business, target_business in rows
        ]

    async def authorized_persons(
        self, db: AsyncSession, tenant_id: str, business_id: str
    ) -> list[dict[str, Any]]:
        values = (
            await db.scalars(
                select(BusinessPerson).where(
                    BusinessPerson.tenant_id == tenant_id,
                    BusinessPerson.business_id == business_id,
                    BusinessPerson.authorization_status == "ACTIVE",
                ).order_by(BusinessPerson.display_name)
            )
        ).all()
        return [self.person_projection(value) for value in values]

    async def audit(self, db: AsyncSession, scope: BrowserScope) -> list[dict[str, Any]]:
        values = (
            await db.scalars(
                select(AuditEvent)
                .where(AuditEvent.tenant_id == scope.tenant_id)
                .order_by(AuditEvent.occurred_at.desc())
                .limit(150)
            )
        ).all()
        return [self.audit_projection(value) for value in values]

    @staticmethod
    def _identity_hash(value: Business) -> str:
        return canonical_hash({
            "id": value.id,
            "tenant_id": value.tenant_id,
            "business_id": value.business_id,
            "registry_number": value.registry_number,
            "business_type": value.business_type,
            "legal_name": value.legal_name,
            "trade_name": value.trade_name,
            "incorporation_date": value.incorporation_date,
            "status": value.status,
            "registered_state_code": value.registered_state_code,
            "registered_address": value.registered_address,
            "industry_code": value.industry_code,
            "msme_classification": value.msme_classification,
            "primary_gstin": value.primary_gstin,
            "risk_flags": value.risk_flags,
            "version": value.version,
        })

    @staticmethod
    async def _business(
        db: AsyncSession, tenant_id: str, identifier: str, *, lock: bool = False
    ) -> Business:
        statement = select(Business).where(
            Business.tenant_id == tenant_id,
            or_(
                Business.id == identifier,
                Business.business_id == identifier,
                Business.registry_number == identifier,
                Business.primary_gstin == identifier.upper(),
            ),
        )
        if lock:
            statement = statement.with_for_update()
        value = await db.scalar(statement.limit(1))
        if value is None:
            raise RegistryNotFoundError("Business record was not found in the tenant scope.")
        return value

    @staticmethod
    def business_summary(value: Business) -> dict[str, Any]:
        return {
            "id": value.id, "business_id": value.business_id,
            "registry_number": value.registry_number, "business_type": value.business_type,
            "legal_name": value.legal_name, "trade_name": value.trade_name,
            "status": value.status, "registered_state_code": value.registered_state_code,
            "msme_classification": value.msme_classification, "primary_gstin": value.primary_gstin,
            "risk_flags": value.risk_flags, "version": value.version,
            "updated_at": iso(value.updated_at),
        }

    @classmethod
    def business_projection(cls, value: Business) -> dict[str, Any]:
        return {
            **cls.business_summary(value),
            "tenant_id": value.tenant_id,
            "incorporation_date": value.incorporation_date.isoformat(),
            "registered_address": value.registered_address,
            "industry_code": value.industry_code,
            "pan_token": value.pan_token,
            "source_hash": value.source_hash,
            "created_by": value.created_by,
            "updated_by": value.updated_by,
            "created_at": iso(value.created_at),
        }

    @staticmethod
    def name_projection(value: BusinessName) -> dict[str, Any]:
        return {
            "id": value.id, "name_type": value.name_type, "name": value.name,
            "effective_from": value.effective_from.isoformat(),
            "effective_to": value.effective_to.isoformat() if value.effective_to else None,
            "source_hash": value.source_hash, "record_version": value.record_version,
        }

    @staticmethod
    def address_projection(value: BusinessAddress) -> dict[str, Any]:
        return {
            "id": value.id, "address_type": value.address_type, "address": value.address_json,
            "verification_status": value.verification_status,
            "effective_from": value.effective_from.isoformat(),
            "effective_to": value.effective_to.isoformat() if value.effective_to else None,
            "source_hash": value.source_hash, "record_version": value.record_version,
        }

    @staticmethod
    def person_projection(value: BusinessPerson) -> dict[str, Any]:
        return {
            "id": value.id, "person_token": value.person_token, "display_name": value.display_name,
            "role": value.role, "appointment_date": value.appointment_date.isoformat(),
            "cessation_date": value.cessation_date.isoformat() if value.cessation_date else None,
            "authorization_status": value.authorization_status,
            "verification_status": value.verification_status,
            "source_hash": value.source_hash, "version": value.version,
        }

    @staticmethod
    def ownership_projection(value: OwnershipLink) -> dict[str, Any]:
        return {
            "id": value.id, "owner_type": value.owner_type, "owner_token": value.owner_token,
            "owner_display_name": value.owner_display_name,
            "ownership_percentage": str(value.ownership_percentage),
            "effective_from": value.effective_from.isoformat(),
            "effective_to": value.effective_to.isoformat() if value.effective_to else None,
            "verification_status": value.verification_status,
            "source_hash": value.source_hash, "version": value.version,
        }

    @staticmethod
    def relationship_projection(value: BusinessRelationship) -> dict[str, Any]:
        return {
            "id": value.id, "source_business_id": value.source_business_id,
            "target_business_id": value.target_business_id,
            "relationship_type": value.relationship_type, "status": value.status,
            "effective_from": value.effective_from.isoformat(),
            "effective_to": value.effective_to.isoformat() if value.effective_to else None,
            "evidence_hash": value.evidence_hash, "version": value.version,
        }

    @staticmethod
    def change_projection(value: ChangeRequest) -> dict[str, Any]:
        return {
            "id": value.id, "business_id": value.business_id,
            "target_version": value.target_version, "requested_patch": value.requested_patch,
            "reason": value.reason, "status": value.status,
            "requested_by": value.requested_by, "reviewed_by": value.reviewed_by,
            "decision_reason": value.decision_reason, "applied_version": value.applied_version,
            "created_at": iso(value.created_at), "decided_at": iso(value.decided_at),
        }

    @staticmethod
    def audit_projection(value: AuditEvent) -> dict[str, Any]:
        return {
            "id": value.id, "event_type": value.event_type,
            "aggregate_type": value.aggregate_type, "aggregate_id": value.aggregate_id,
            "version": value.aggregate_version, "actor_type": value.actor_type,
            "actor_id": value.actor_id, "reason": value.reason,
            "metadata": value.metadata_json, "occurred_at": iso(value.occurred_at),
        }


registry_service = RegistryService()
