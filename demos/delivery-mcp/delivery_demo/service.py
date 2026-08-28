import hashlib
import hmac
import json
import secrets
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import ActorScope
from .constants import PENDING_ACCEPTANCE_STATUSES, TERMINAL_STATUSES
from .database import session
from .models import (
    AuditEvent,
    BuyerAcceptance,
    Delivery,
    DeliveryCorrection,
    DeliveryEvent,
    DeliveryItem,
    ExternalAggregateVersion,
    InboxEvent,
    OutboxEvent,
    ProofOfDelivery,
)
from .schemas import (
    AcceptanceCreate,
    CorrectionCreate,
    DeliveryAttemptRequest,
    DeliveryCreate,
    DispatchRequest,
    ExternalEventEnvelope,
    FulfilmentClaim,
    ProofCreate,
    TransitEventRequest,
)
from .settings import get_settings


class DeliveryDemoDomainError(RuntimeError):
    status_code = 400


class DeliveryNotFoundError(DeliveryDemoDomainError):
    status_code = 404


class DeliveryConflictError(DeliveryDemoDomainError):
    status_code = 409


class DeliveryDemoService:
    @staticmethod
    def _hash(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()

    @staticmethod
    def _snapshot(delivery: Delivery) -> dict[str, Any]:
        return {
            "id": delivery.id,
            "tenant_id": delivery.tenant_id,
            "delivery_number": delivery.delivery_number,
            "purchase_order_id": delivery.purchase_order_id,
            "invoice_id": delivery.invoice_id,
            "status": delivery.status,
            "carrier_id": delivery.carrier_id,
            "tracking_number": delivery.tracking_number,
            "verified_delivered_value": str(delivery.verified_delivered_value),
            "exception_code": delivery.exception_code,
            "version": delivery.version,
        }

    async def _delivery(
        self, db: AsyncSession, tenant_id: str, delivery_id: str, *, lock: bool = False
    ) -> Delivery:
        query = select(Delivery).where(
            Delivery.id == delivery_id, Delivery.tenant_id == tenant_id
        )
        if lock:
            query = query.with_for_update()
        delivery = await db.scalar(query)
        if delivery is None:
            raise DeliveryNotFoundError("Delivery not found.")
        return delivery

    @staticmethod
    def _expect_version(delivery: Delivery, expected_version: int) -> None:
        if delivery.version != expected_version:
            raise DeliveryConflictError(
                f"Delivery version is {delivery.version}; refresh and retry with If-Match: {delivery.version}."
            )

    async def _tracking_number(self, db: AsyncSession, tenant_id: str) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        for _ in range(20):
            candidate = "XY" + "".join(secrets.choice(alphabet) for _ in range(8))
            exists = await db.scalar(
                select(Delivery.id).where(
                    Delivery.tenant_id == tenant_id,
                    Delivery.tracking_number == candidate,
                )
            )
            if not exists:
                return candidate
        raise DeliveryConflictError("A unique tracking number could not be generated.")

    def _record(
        self,
        db: AsyncSession,
        delivery: Delivery,
        event_type: str,
        actor: ActorScope,
        before: dict[str, Any] | None,
        *,
        reason: str | None = None,
        detail: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        correlation_id = correlation_id or f"corr_{uuid4().hex}"
        after = self._snapshot(delivery)
        db.add(
            AuditEvent(
                id=str(uuid4()),
                tenant_id=delivery.tenant_id,
                application_id="xyena-demo-delivery",
                aggregate_type="delivery",
                aggregate_id=delivery.id,
                aggregate_version=delivery.version,
                event_type=event_type,
                actor_type="SERVICE" if actor.role == "SERVICE" else "USER",
                actor_id=actor.actor_id,
                reason=reason,
                before_hash=self._hash(before) if before is not None else None,
                after_hash=self._hash(after),
                detail=json.dumps(detail or {}, sort_keys=True, default=str),
                correlation_id=correlation_id,
            )
        )
        db.add(
            OutboxEvent(
                id=f"evt_{uuid4().hex}",
                tenant_id=delivery.tenant_id,
                aggregate_type="delivery",
                aggregate_id=delivery.id,
                aggregate_version=delivery.version,
                event_type=event_type,
                schema_version="1.0",
                payload=json.dumps(
                    {"delivery_id": delivery.id, "status": delivery.status, "version": delivery.version},
                    sort_keys=True,
                ),
                correlation_id=correlation_id,
            )
        )

    def _timeline(
        self,
        db: AsyncSession,
        delivery: Delivery,
        event_type: str,
        actor: ActorScope,
        prior_status: str | None,
        *,
        location: dict[str, Any] | None = None,
        notes: str | None = None,
        occurred_at: datetime | None = None,
        correlation_id: str | None = None,
    ) -> None:
        db.add(
            DeliveryEvent(
                id=str(uuid4()),
                delivery_id=delivery.id,
                event_type=event_type,
                occurred_at=occurred_at or datetime.now(UTC),
                actor=actor.actor_id,
                location=json.dumps(location, sort_keys=True) if location else None,
                notes=notes,
                prior_status=prior_status,
                new_status=delivery.status,
                version=delivery.version,
                correlation_id=correlation_id,
            )
        )

    async def create_delivery(
        self, actor: ActorScope, body: DeliveryCreate, correlation_id: str | None = None
    ) -> Delivery:
        async with session() as db:
            duplicate = await db.scalar(
                select(Delivery.id).where(
                    Delivery.tenant_id == actor.tenant_id,
                    Delivery.delivery_number == body.delivery_number,
                )
            )
            if duplicate:
                raise DeliveryConflictError("Delivery number already exists in this tenant.")
            delivery = Delivery(
                id=str(uuid4()),
                tenant_id=actor.tenant_id,
                delivery_number=body.delivery_number,
                purchase_order_id=body.purchase_order_id,
                invoice_id=body.invoice_id,
                invoice_number=body.invoice_number,
                seller_business_id=body.seller_business_id,
                seller_gstin=body.seller_gstin,
                buyer_id=body.buyer_id,
                buyer_gstin=body.buyer_gstin,
                status="CREATED",
                ship_from=body.ship_from.model_dump_json(),
                ship_to=body.ship_to.model_dump_json(),
                expected_delivery_date=body.expected_delivery_date,
                currency=body.currency,
                declared_value=body.declared_value,
                verified_delivered_value=Decimal("0"),
                version=1,
                created_by=actor.actor_id,
                updated_by=actor.actor_id,
            )
            db.add(delivery)
            for item in body.items:
                db.add(
                    DeliveryItem(
                        id=str(uuid4()), delivery_id=delivery.id,
                        po_line_id=item.po_line_id, invoice_line_id=item.invoice_line_id,
                        sku=item.sku, description=item.description, unit=item.unit,
                        ordered_quantity=item.ordered_quantity,
                        dispatched_quantity=Decimal("0"), delivered_quantity=Decimal("0"),
                        accepted_quantity=Decimal("0"), rejected_quantity=Decimal("0"),
                        supported_unit_value=item.supported_unit_value, version=1,
                    )
                )
            self._timeline(db, delivery, "delivery.created", actor, None, correlation_id=correlation_id)
            self._record(db, delivery, "delivery.created", actor, None, correlation_id=correlation_id)
            return delivery

    async def mark_ready(
        self, actor: ActorScope, delivery_id: str, expected_version: int
    ) -> Delivery:
        async with session() as db:
            delivery = await self._delivery(db, actor.tenant_id, delivery_id, lock=True)
            self._expect_version(delivery, expected_version)
            if delivery.status != "CREATED":
                raise DeliveryConflictError("Only a CREATED delivery can be marked ready.")
            if not delivery.purchase_order_id or not delivery.seller_business_id or not delivery.buyer_id:
                raise DeliveryConflictError("Purchase order, seller and buyer identities are required.")
            before, prior = self._snapshot(delivery), delivery.status
            delivery.tracking_number = await self._tracking_number(db, actor.tenant_id)
            delivery.status = "READY_TO_DISPATCH"
            delivery.version += 1
            delivery.updated_by = actor.actor_id
            self._timeline(db, delivery, "delivery.ready", actor, prior)
            self._record(db, delivery, "delivery.ready", actor, before)
            return delivery

    async def dispatch_delivery(
        self, actor: ActorScope, delivery_id: str, expected_version: int, body: DispatchRequest
    ) -> Delivery:
        async with session() as db:
            delivery = await self._delivery(db, actor.tenant_id, delivery_id, lock=True)
            self._expect_version(delivery, expected_version)
            if delivery.status != "READY_TO_DISPATCH" or not delivery.tracking_number:
                raise DeliveryConflictError("Delivery must be ready with a server-issued tracking number.")
            items = (await db.scalars(select(DeliveryItem).where(DeliveryItem.delivery_id == delivery.id).with_for_update())).all()
            known = {item.sku for item in items}
            if set(body.item_quantities) != known:
                raise DeliveryDemoDomainError("Dispatch quantities must include every delivery SKU exactly once.")
            for item in items:
                quantity = body.item_quantities[item.sku]
                if quantity > item.ordered_quantity:
                    raise DeliveryDemoDomainError(f"Dispatch for {item.sku} exceeds ordered quantity.")
                item.dispatched_quantity = quantity
                item.version += 1
            before, prior = self._snapshot(delivery), delivery.status
            delivery.carrier_id = body.carrier_id
            delivery.dispatch_date = datetime.now(UTC)
            delivery.status = "DISPATCHED"
            delivery.version += 1
            delivery.updated_by = actor.actor_id
            self._timeline(db, delivery, "delivery.dispatched", actor, prior)
            self._record(db, delivery, "delivery.dispatched", actor, before)
            return delivery

    async def record_transit_event(
        self, actor: ActorScope, delivery_id: str, expected_version: int, body: TransitEventRequest
    ) -> Delivery:
        async with session() as db:
            delivery = await self._delivery(db, actor.tenant_id, delivery_id, lock=True)
            self._expect_version(delivery, expected_version)
            transitions = {
                ("DISPATCHED", "IN_TRANSIT"): "IN_TRANSIT",
                ("IN_TRANSIT", "OUT_FOR_DELIVERY"): "OUT_FOR_DELIVERY",
                ("DISPATCHED", "DELIVERY_DELAYED"): "DELIVERY_FAILED",
                ("IN_TRANSIT", "DELIVERY_DELAYED"): "DELIVERY_FAILED",
                ("OUT_FOR_DELIVERY", "DELIVERY_DELAYED"): "DELIVERY_FAILED",
                ("DELIVERY_FAILED", "DELIVERY_RESUMED"): "IN_TRANSIT",
            }
            target = transitions.get((delivery.status, body.event_type))
            if target is None:
                raise DeliveryConflictError(f"{body.event_type} is invalid from {delivery.status}.")
            occurred_at = body.occurred_at or datetime.now(UTC)
            if occurred_at > datetime.now(UTC) + timedelta(minutes=5):
                raise DeliveryDemoDomainError("Transit event cannot be in the future.")
            dispatch_date = delivery.dispatch_date
            if dispatch_date and dispatch_date.tzinfo is None:
                dispatch_date = dispatch_date.replace(tzinfo=UTC)
            if dispatch_date and occurred_at < dispatch_date:
                raise DeliveryDemoDomainError("Transit event cannot predate dispatch.")
            before, prior = self._snapshot(delivery), delivery.status
            delivery.status = target
            delivery.exception_code = "DELIVERY_DELAYED" if target == "DELIVERY_FAILED" else None
            delivery.version += 1
            delivery.updated_by = actor.actor_id
            self._timeline(db, delivery, f"delivery.{body.event_type.lower()}", actor, prior, location=body.location.model_dump() if body.location else None, notes=body.notes, occurred_at=occurred_at)
            self._record(db, delivery, f"delivery.{body.event_type.lower()}", actor, before)
            return delivery

    async def record_delivery_attempt(
        self, actor: ActorScope, delivery_id: str, expected_version: int, body: DeliveryAttemptRequest
    ) -> Delivery:
        async with session() as db:
            delivery = await self._delivery(db, actor.tenant_id, delivery_id, lock=True)
            self._expect_version(delivery, expected_version)
            if delivery.status not in {"IN_TRANSIT", "OUT_FOR_DELIVERY"}:
                raise DeliveryConflictError("Delivery attempt requires IN_TRANSIT or OUT_FOR_DELIVERY status.")
            items = (await db.scalars(select(DeliveryItem).where(DeliveryItem.delivery_id == delivery.id).with_for_update())).all()
            before, prior = self._snapshot(delivery), delivery.status
            if body.success:
                if set(body.item_quantities) != {item.sku for item in items}:
                    raise DeliveryDemoDomainError("Delivered quantities must include every SKU exactly once.")
                partial = False
                for item in items:
                    quantity = body.item_quantities[item.sku]
                    if quantity > item.dispatched_quantity:
                        raise DeliveryDemoDomainError(f"Delivered quantity for {item.sku} exceeds dispatch.")
                    item.delivered_quantity = quantity
                    item.version += 1
                    partial = partial or quantity < item.dispatched_quantity
                delivery.delivered_at = datetime.now(UTC)
                delivery.status = "PARTIAL_PENDING_ACCEPTANCE" if partial else "DELIVERED_PENDING_ACCEPTANCE"
                delivery.exception_code = "SHORT_DELIVERY" if partial else None
            else:
                delivery.status = "DELIVERY_FAILED"
                delivery.exception_code = "ATTEMPT_FAILED"
            delivery.version += 1
            delivery.updated_by = actor.actor_id
            self._timeline(db, delivery, "delivery.attempt_succeeded" if body.success else "delivery.attempt_failed", actor, prior, notes=body.failure_reason)
            self._record(db, delivery, "delivery.attempt_succeeded" if body.success else "delivery.attempt_failed", actor, before, reason=body.failure_reason)
            return delivery

    async def capture_pod(
        self, actor: ActorScope, delivery_id: str, expected_version: int, body: ProofCreate
    ) -> ProofOfDelivery:
        async with session() as db:
            delivery = await self._delivery(db, actor.tenant_id, delivery_id, lock=True)
            self._expect_version(delivery, expected_version)
            if delivery.status not in PENDING_ACCEPTANCE_STATUSES:
                raise DeliveryConflictError("Proof can only be captured after a successful delivery attempt.")
            existing = (await db.scalars(select(ProofOfDelivery).where(
                ProofOfDelivery.delivery_id == delivery.id,
                ProofOfDelivery.verification_status == "PENDING_VERIFICATION",
            ).with_for_update())).all()
            proof_id = str(uuid4())
            for proof in existing:
                proof.verification_status = "REJECTED"
                proof.replacement_link = proof_id
            proof = ProofOfDelivery(
                id=proof_id, delivery_id=delivery.id, proof_type=body.proof_type,
                restricted_object_key=body.restricted_object_key,
                content_hash=body.content_hash.lower(), mime_type=body.mime_type,
                recipient_token=body.recipient_token, recipient_name=None,
                recipient_role=body.recipient_role,
                verification_status="PENDING_VERIFICATION",
                security_flags=json.dumps(body.security_flags),
            )
            db.add(proof)
            before, prior = self._snapshot(delivery), delivery.status
            delivery.version += 1
            delivery.updated_by = actor.actor_id
            self._timeline(db, delivery, "delivery.proof_captured", actor, prior)
            self._record(db, delivery, "delivery.proof_captured", actor, before, detail={"proof_id": proof.id, "content_hash": proof.content_hash})
            return proof

    async def verify_pod(
        self, actor: ActorScope, delivery_id: str, proof_id: str, expected_version: int,
        verified: bool, rejection_reason: str | None,
    ) -> Delivery:
        async with session() as db:
            delivery = await self._delivery(db, actor.tenant_id, delivery_id, lock=True)
            self._expect_version(delivery, expected_version)
            proof = await db.scalar(select(ProofOfDelivery).where(
                ProofOfDelivery.id == proof_id, ProofOfDelivery.delivery_id == delivery.id
            ).with_for_update())
            if proof is None:
                raise DeliveryNotFoundError("Proof not found.")
            if proof.verification_status != "PENDING_VERIFICATION":
                raise DeliveryConflictError("Only pending proof can be reviewed.")
            before, prior = self._snapshot(delivery), delivery.status
            proof.verification_status = "VERIFIED" if verified else "REJECTED"
            proof.verification_method = "INDEPENDENT_REVIEW"
            proof.verifier = actor.actor_id
            if not verified:
                flags = json.loads(proof.security_flags or "[]")
                flags.append("REVIEW_REJECTED")
                proof.security_flags = json.dumps(sorted(set(flags)))
            delivery.version += 1
            delivery.updated_by = actor.actor_id
            self._timeline(db, delivery, "delivery.proof_verified" if verified else "delivery.proof_rejected", actor, prior, notes=rejection_reason)
            self._record(db, delivery, "delivery.proof_verified" if verified else "delivery.proof_rejected", actor, before, reason=rejection_reason, detail={"proof_id": proof.id})
            return delivery

    async def record_buyer_acceptance(
        self, actor: ActorScope, delivery_id: str, expected_version: int, body: AcceptanceCreate
    ) -> Delivery:
        async with session() as db:
            delivery = await self._delivery(db, actor.tenant_id, delivery_id, lock=True)
            self._expect_version(delivery, expected_version)
            if delivery.status not in PENDING_ACCEPTANCE_STATUSES:
                raise DeliveryConflictError("Acceptance requires a delivery pending acceptance.")
            verified = await db.scalar(select(ProofOfDelivery.id).where(
                ProofOfDelivery.delivery_id == delivery.id,
                ProofOfDelivery.verification_status == "VERIFIED",
            ))
            if not verified:
                raise DeliveryConflictError("Buyer acceptance requires independently verified proof of delivery.")
            items = (await db.scalars(select(DeliveryItem).where(DeliveryItem.delivery_id == delivery.id).with_for_update())).all()
            supplied = {entry.sku: entry for entry in body.items}
            if len(supplied) != len(body.items) or set(supplied) != {item.sku for item in items}:
                raise DeliveryDemoDomainError("Acceptance must include every SKU exactly once.")
            accepted_value = Decimal("0")
            any_accepted = any_rejected = False
            snapshot: list[dict[str, Any]] = []
            for item in items:
                entry = supplied[item.sku]
                if entry.accepted_quantity + entry.rejected_quantity != item.delivered_quantity:
                    raise DeliveryDemoDomainError(f"Acceptance quantities for {item.sku} must equal delivered quantity.")
                if entry.rejected_quantity and not entry.reason:
                    raise DeliveryDemoDomainError(f"Rejected quantity for {item.sku} requires a reason.")
                item.accepted_quantity = entry.accepted_quantity
                item.rejected_quantity = entry.rejected_quantity
                item.rejection_reason = entry.reason
                item.version += 1
                accepted_value += entry.accepted_quantity * item.supported_unit_value
                any_accepted = any_accepted or entry.accepted_quantity > 0
                any_rejected = any_rejected or entry.rejected_quantity > 0
                snapshot.append({"sku": item.sku, "accepted_quantity": str(entry.accepted_quantity), "rejected_quantity": str(entry.rejected_quantity), "reason": entry.reason})
            before, prior = self._snapshot(delivery), delivery.status
            status = "PARTIALLY_ACCEPTED" if any_accepted and any_rejected else "DELIVERED" if any_accepted else "REJECTED"
            delivery.status = status
            delivery.verified_delivered_value = accepted_value.quantize(Decimal("0.01"))
            delivery.version += 1
            delivery.updated_by = actor.actor_id
            db.add(BuyerAcceptance(
                id=str(uuid4()), delivery_id=delivery.id, version=delivery.version,
                buyer_identity=delivery.buyer_id, status="ACCEPTED" if status == "DELIVERED" else status,
                accepted_value=delivery.verified_delivered_value,
                item_level_acceptance=json.dumps(snapshot, sort_keys=True), actor=actor.actor_id,
                reason=body.reason, source_hash=self._hash(snapshot),
            ))
            self._timeline(db, delivery, "delivery.accepted", actor, prior)
            self._record(db, delivery, "delivery.accepted", actor, before, reason=body.reason)
            return delivery

    async def cancel_delivery(
        self, actor: ActorScope, delivery_id: str, expected_version: int, reason: str
    ) -> Delivery:
        async with session() as db:
            delivery = await self._delivery(db, actor.tenant_id, delivery_id, lock=True)
            self._expect_version(delivery, expected_version)
            if delivery.status in TERMINAL_STATUSES:
                raise DeliveryConflictError("A terminal delivery cannot be cancelled.")
            if delivery.status not in {"CREATED", "READY_TO_DISPATCH"} and actor.role != "DELIVERY_REVIEWER":
                raise DeliveryConflictError("Post-dispatch cancellation requires independent reviewer approval.")
            before, prior = self._snapshot(delivery), delivery.status
            delivery.status = "CANCELLED"
            delivery.exception_code = "CANCELLED_BY_REVIEWER" if actor.role == "DELIVERY_REVIEWER" else None
            delivery.version += 1
            delivery.updated_by = actor.actor_id
            self._timeline(db, delivery, "delivery.cancelled", actor, prior, notes=reason)
            self._record(db, delivery, "delivery.cancelled", actor, before, reason=reason)
            return delivery

    async def propose_correction(
        self, actor: ActorScope, delivery_id: str, expected_version: int, body: CorrectionCreate
    ) -> DeliveryCorrection:
        allowed = {
            "IDENTITY": {"seller_business_id", "seller_gstin", "buyer_id", "buyer_gstin"},
            "REFERENCE": {"purchase_order_id", "invoice_id", "invoice_number"},
            "TRACKING": {"tracking_number", "carrier_id"},
            "ADDRESS": {"ship_from", "ship_to"},
        }[body.correction_type]
        if not body.proposed_changes or not set(body.proposed_changes).issubset(allowed):
            raise DeliveryDemoDomainError("Correction contains fields outside its approved type.")
        async with session() as db:
            delivery = await self._delivery(db, actor.tenant_id, delivery_id, lock=True)
            self._expect_version(delivery, expected_version)
            pending = await db.scalar(select(DeliveryCorrection.id).where(
                DeliveryCorrection.delivery_id == delivery.id,
                DeliveryCorrection.status == "PENDING",
            ))
            if pending:
                raise DeliveryConflictError("This delivery already has a pending correction.")
            before, prior = self._snapshot(delivery), delivery.status
            correction = DeliveryCorrection(
                id=str(uuid4()), delivery_id=delivery.id, aggregate_version=delivery.version,
                correction_type=body.correction_type,
                proposed_changes=json.dumps(body.proposed_changes, sort_keys=True),
                reason=body.reason, requester=actor.actor_id, decision="PENDING", status="PENDING",
            )
            db.add(correction)
            delivery.version += 1
            delivery.updated_by = actor.actor_id
            self._timeline(db, delivery, "delivery.correction_proposed", actor, prior, notes=body.reason)
            self._record(db, delivery, "delivery.correction_proposed", actor, before, reason=body.reason, detail={"correction_id": correction.id})
            return correction

    async def review_correction(
        self, actor: ActorScope, correction_id: str, expected_version: int,
        approve: bool, reason: str | None,
    ) -> Delivery:
        async with session() as db:
            correction = await db.scalar(select(DeliveryCorrection).where(DeliveryCorrection.id == correction_id).with_for_update())
            if correction is None:
                raise DeliveryNotFoundError("Correction not found.")
            delivery = await self._delivery(db, actor.tenant_id, correction.delivery_id, lock=True)
            self._expect_version(delivery, expected_version)
            if correction.status != "PENDING":
                raise DeliveryConflictError("Correction has already been reviewed.")
            before, prior = self._snapshot(delivery), delivery.status
            correction.reviewer = actor.actor_id
            correction.decision = "APPROVED" if approve else "REJECTED"
            correction.status = correction.decision
            if approve:
                changes = json.loads(correction.proposed_changes)
                if "tracking_number" in changes:
                    tracking = changes["tracking_number"]
                    if not isinstance(tracking, str) or len(tracking) != 10 or not tracking.startswith("XY"):
                        raise DeliveryDemoDomainError("Replacement tracking must be a 10-character XY identifier.")
                    duplicate = await db.scalar(select(Delivery.id).where(
                        Delivery.tenant_id == actor.tenant_id,
                        Delivery.tracking_number == tracking,
                        Delivery.id != delivery.id,
                    ))
                    if duplicate:
                        raise DeliveryConflictError("Tracking number already exists.")
                for field, value in changes.items():
                    if field in {"ship_from", "ship_to"}:
                        json.loads(value)
                    setattr(delivery, field, value)
            delivery.version += 1
            delivery.updated_by = actor.actor_id
            if approve:
                correction.applied_version = delivery.version
            self._timeline(db, delivery, "delivery.correction_approved" if approve else "delivery.correction_rejected", actor, prior, notes=reason)
            self._record(db, delivery, "delivery.correction_approved" if approve else "delivery.correction_rejected", actor, before, reason=reason, detail={"correction_id": correction.id, "changes": json.loads(correction.proposed_changes)})
            return delivery

    async def consume_external_event(
        self, envelope: ExternalEventEnvelope, payload_hash: str
    ) -> str:
        async with session() as db:
            duplicate = await db.scalar(select(InboxEvent).where(
                InboxEvent.source_application == envelope.source_application,
                InboxEvent.event_id == envelope.event_id,
            ))
            if duplicate:
                return "DUPLICATE"
            version_row = await db.scalar(select(ExternalAggregateVersion).where(
                ExternalAggregateVersion.tenant_id == envelope.tenant_id,
                ExternalAggregateVersion.source_application == envelope.source_application,
                ExternalAggregateVersion.aggregate_type == envelope.aggregate.type,
                ExternalAggregateVersion.aggregate_id == envelope.aggregate.id,
            ).with_for_update())
            if version_row and envelope.aggregate.version <= version_row.latest_version:
                status = "STALE"
            else:
                status = "PROCESSED"
                if version_row:
                    version_row.latest_version = envelope.aggregate.version
                else:
                    db.add(ExternalAggregateVersion(
                        id=str(uuid4()), tenant_id=envelope.tenant_id,
                        source_application=envelope.source_application,
                        aggregate_type=envelope.aggregate.type,
                        aggregate_id=envelope.aggregate.id,
                        latest_version=envelope.aggregate.version,
                    ))
                query = select(Delivery).where(Delivery.tenant_id == envelope.tenant_id)
                if envelope.aggregate.type == "purchase_order":
                    query = query.where(Delivery.purchase_order_id == envelope.aggregate.id)
                elif envelope.aggregate.type == "invoice":
                    query = query.where(Delivery.invoice_id == envelope.aggregate.id)
                else:
                    query = query.where(or_(Delivery.seller_business_id == envelope.aggregate.id, Delivery.buyer_id == envelope.aggregate.id))
                for delivery in (await db.scalars(query.with_for_update())).all():
                    if delivery.status not in TERMINAL_STATUSES:
                        before, prior = self._snapshot(delivery), delivery.status
                        delivery.exception_code = {
                            "purchase_order.cancelled": "SOURCE_PO_CANCELLED",
                            "invoice.cancelled": "SOURCE_INVOICE_CANCELLED",
                            "business.updated": "SOURCE_IDENTITY_CHANGED",
                        }[envelope.event_type]
                        delivery.version += 1
                        delivery.updated_by = envelope.source_application
                        source_actor = ActorScope(
                            envelope.tenant_id,
                            envelope.source_application,
                            "SERVICE",
                        )
                        self._timeline(
                            db,
                            delivery,
                            envelope.event_type,
                            source_actor,
                            prior,
                            occurred_at=envelope.occurred_at,
                            correlation_id=envelope.correlation_id,
                        )
                        self._record(
                            db,
                            delivery,
                            envelope.event_type,
                            source_actor,
                            before,
                            detail={
                                "source_event_id": envelope.event_id,
                                "source_aggregate_version": envelope.aggregate.version,
                            },
                            correlation_id=envelope.correlation_id,
                        )
            db.add(InboxEvent(
                source_application=envelope.source_application, event_id=envelope.event_id,
                tenant_id=envelope.tenant_id, event_type=envelope.event_type,
                aggregate_type=envelope.aggregate.type, aggregate_id=envelope.aggregate.id,
                aggregate_version=envelope.aggregate.version, status=status,
                payload_hash=payload_hash, processed_at=datetime.now(UTC),
            ))
            return status

    async def get_delivery(self, tenant_id: str, delivery_id: str) -> dict[str, Any]:
        async with session() as db:
            delivery = await self._delivery(db, tenant_id, delivery_id)
            return {
                "delivery": delivery,
                "items": (await db.scalars(select(DeliveryItem).where(DeliveryItem.delivery_id == delivery_id))).all(),
                "events": (await db.scalars(select(DeliveryEvent).where(DeliveryEvent.delivery_id == delivery_id).order_by(DeliveryEvent.occurred_at))).all(),
                "proofs": (await db.scalars(select(ProofOfDelivery).where(ProofOfDelivery.delivery_id == delivery_id).order_by(ProofOfDelivery.captured_at.desc()))).all(),
                "acceptances": (await db.scalars(select(BuyerAcceptance).where(BuyerAcceptance.delivery_id == delivery_id).order_by(BuyerAcceptance.occurred_at.desc()))).all(),
                "corrections": (await db.scalars(select(DeliveryCorrection).where(DeliveryCorrection.delivery_id == delivery_id).order_by(DeliveryCorrection.aggregate_version.desc()))).all(),
            }

    def source_envelope(
        self, source_system: str, request_id: str, record_version: int, data: Any,
        updated_at: datetime | None = None,
    ) -> dict[str, Any]:
        retrieved_at = datetime.now(UTC)
        envelope = {
            "schema_version": "1.0", "source_system": source_system,
            "request_id": request_id, "record_version": record_version,
            "updated_at": (updated_at or retrieved_at).isoformat(),
            "retrieved_at": retrieved_at.isoformat(),
            "fresh_until": (retrieved_at + timedelta(minutes=15)).isoformat(),
            "data": data, "security_labels": ["SYNTHETIC_DATA", "TENANT_SCOPED"],
            "source_signature_algorithm": "hmac-sha256",
        }
        canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"), default=str).encode()
        envelope["source_signature"] = hmac.new(
            get_settings().source_signing_key.get_secret_value().encode(), canonical, hashlib.sha256
        ).hexdigest()
        return envelope

    async def verify_fulfilment(
        self, tenant_id: str, claims: list[FulfilmentClaim]
    ) -> dict[str, Any]:
        matches, unmatched, contradictions = [], [], []
        max_version = 0
        async with session() as db:
            for claim in claims:
                query = select(DeliveryItem, Delivery).join(Delivery, Delivery.id == DeliveryItem.delivery_id).where(
                    Delivery.tenant_id == tenant_id,
                    Delivery.purchase_order_id == claim.purchase_order_id,
                    Delivery.invoice_id == claim.invoice_id,
                    Delivery.status.in_(["DELIVERED", "PARTIALLY_ACCEPTED"]),
                    exists(
                        select(ProofOfDelivery.id).where(
                            ProofOfDelivery.delivery_id == Delivery.id,
                            ProofOfDelivery.verification_status == "VERIFIED",
                        )
                    ),
                )
                if claim.po_line_id:
                    query = query.where(DeliveryItem.po_line_id == claim.po_line_id)
                elif claim.invoice_line_id:
                    query = query.where(DeliveryItem.invoice_line_id == claim.invoice_line_id)
                else:
                    query = query.where(DeliveryItem.sku == claim.sku)
                rows = (await db.execute(query)).all()
                identity = claim.po_line_id or claim.invoice_line_id or claim.sku
                if not rows:
                    unmatched.append({"line_identity": identity, "reason": "No accepted delivery line matched all invoice and PO identities."})
                    continue
                accepted = sum((row[0].accepted_quantity for row in rows), Decimal("0"))
                unit_values = {row[0].supported_unit_value for row in rows}
                versions = sorted({row[1].version for row in rows})
                max_version = max(max_version, *versions)
                errors = []
                if accepted != claim.claimed_quantity:
                    errors.append({"code": "QUANTITY_MISMATCH", "supported": str(accepted)})
                if unit_values != {claim.claimed_unit_value}:
                    errors.append({"code": "VALUE_MISMATCH", "supported": sorted(str(v) for v in unit_values)})
                result = {
                    "purchase_order_id": claim.purchase_order_id,
                    "invoice_id": claim.invoice_id,
                    "line_identity": identity,
                    "claimed_quantity": str(claim.claimed_quantity),
                    "accepted_quantity": str(accepted),
                    "claimed_unit_value": str(claim.claimed_unit_value),
                    "supported_unit_values": sorted(str(v) for v in unit_values),
                    "source_versions": versions,
                }
                (contradictions if errors else matches).append({**result, **({"errors": errors} if errors else {})})
        return {"matches": matches, "unmatched_lines": unmatched, "contradiction_lines": contradictions, "record_version": max_version}

    async def dashboard(self, tenant_id: str) -> dict[str, Any]:
        async with session() as db:
            deliveries = (await db.scalars(select(Delivery).where(Delivery.tenant_id == tenant_id))).all()
            counts: dict[str, int] = {}
            aging = {"1_day": 0, "3_days": 0, "5_plus_days": 0}
            alerts = []
            for delivery in deliveries:
                counts[delivery.status] = counts.get(delivery.status, 0) + 1
                if delivery.exception_code:
                    alerts.append({"delivery_id": delivery.id, "delivery_number": delivery.delivery_number, "type": delivery.exception_code})
                if delivery.status in {"DISPATCHED", "IN_TRANSIT", "OUT_FOR_DELIVERY"} and delivery.expected_delivery_date:
                    days = (date.today() - delivery.expected_delivery_date).days
                    if days >= 5:
                        aging["5_plus_days"] += 1
                    elif days >= 3:
                        aging["3_days"] += 1
                    elif days >= 1:
                        aging["1_day"] += 1
            audits = (await db.scalars(select(AuditEvent).where(AuditEvent.tenant_id == tenant_id).order_by(AuditEvent.occurred_at.desc()).limit(10))).all()
            return {
                "counts": counts,
                "total_accepted_value": str(sum((d.verified_delivered_value for d in deliveries), Decimal("0"))),
                "total_declared_value": str(sum((d.declared_value for d in deliveries), Decimal("0"))),
                "aging_report": aging, "alerts": alerts,
                "recent_audit_trail": [{"id": a.id, "event_type": a.event_type, "aggregate_id": a.aggregate_id, "actor_id": a.actor_id, "occurred_at": a.occurred_at.isoformat()} for a in audits],
            }

    async def list_deliveries(
        self, tenant_id: str, search: str | None = None, status: str | None = None
    ) -> list[Delivery]:
        async with session() as db:
            query = select(Delivery).where(Delivery.tenant_id == tenant_id)
            if search:
                query = query.where(or_(Delivery.delivery_number.contains(search), Delivery.purchase_order_id.contains(search), Delivery.invoice_number.contains(search)))
            if status:
                query = query.where(Delivery.status == status)
            return list((await db.scalars(query.order_by(Delivery.created_at.desc()))).all())


delivery_service = DeliveryDemoService()
