import asyncio
import hashlib
import hmac
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import session
from .models import (
    AuditEvent,
    BuyerAcceptance,
    Delivery,
    DeliveryCorrection,
    DeliveryEvent,
    DeliveryItem,
    InboxEvent,
    OutboxEvent,
    ProofOfDelivery,
)
from .security import RuntimeScope
from .settings import get_settings


class DeliveryDemoDomainError(RuntimeError):
    pass


# Global list of SSE listener queues for real-time notification
sse_listeners: list[asyncio.Queue] = []


def broadcast_sse(event_data: dict[str, Any]) -> None:
    for queue in sse_listeners:
        queue.put_nowait(event_data)


class DeliveryDemoService:
    @staticmethod
    def _hash(value: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()

    def _receipt(self, scope: RuntimeScope, kind: str, refs: list[str]) -> str:
        body = {"call_id": scope.call_id, "kind": kind, "refs": refs}
        signature = hmac.new(
            get_settings().mcp_token.get_secret_value().encode(),
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()[:24]
        return f"evr_demo_{signature}"

    def _audit(
        self,
        db: AsyncSession,
        tenant_id: str,
        aggregate_type: str,
        aggregate_id: str,
        version: int,
        event_type: str,
        actor_type: str,
        actor_id: str,
        reason: str | None = None,
        before_hash: str | None = None,
        after_hash: str | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        db.add(
            AuditEvent(
                id=str(uuid4()),
                tenant_id=tenant_id,
                application_id="xyena-demo-delivery",
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                aggregate_version=version,
                event_type=event_type,
                actor_type=actor_type,
                actor_id=actor_id,
                reason=reason,
                before_hash=before_hash,
                after_hash=after_hash or "0" * 64,
                detail=json.dumps(metadata or {}, sort_keys=True, default=str),
                correlation_id=correlation_id or str(uuid4()),
            )
        )

    def _publish_event(
        self,
        db: AsyncSession,
        tenant_id: str,
        aggregate_type: str,
        aggregate_id: str,
        version: int,
        event_type: str,
        payload: dict[str, Any],
        correlation_id: str | None = None,
    ) -> OutboxEvent:
        evt_id = f"evt_{uuid4().hex[:12]}"
        corr_id = correlation_id or f"corr_{uuid4().hex[:12]}"
        outbox = OutboxEvent(
            id=evt_id,
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=version,
            event_type=event_type,
            schema_version="1.0",
            payload=json.dumps(payload, sort_keys=True, default=str),
            correlation_id=corr_id,
            created_at=datetime.now(UTC),
        )
        db.add(outbox)

        # Broadcast SSE reload signal for reactive UI
        broadcast_sse(
            {
                "event_id": evt_id,
                "event_type": event_type,
                "tenant_id": tenant_id,
                "delivery_id": aggregate_id,
                "correlation_id": corr_id,
                "occurred_at": datetime.now(UTC).isoformat(),
            }
        )
        return outbox

    # --- Domain Workflows ---

    async def create_delivery(
        self,
        tenant_id: str,
        delivery_number: str,
        purchase_order_id: str,
        invoice_id: str | None,
        invoice_number: str | None,
        seller_business_id: str,
        seller_gstin: str,
        buyer_id: str,
        buyer_gstin: str,
        ship_from: dict[str, Any],
        ship_to: dict[str, Any],
        currency: str,
        declared_value: Decimal,
        items_data: list[dict[str, Any]],
        actor: str,
        correlation_id: str | None = None,
    ) -> Delivery:
        if not items_data:
            raise DeliveryDemoDomainError("A delivery must contain at least one item.")

        async with session() as db:
            # Check duplicate delivery number
            existing = await db.scalar(
                select(Delivery).where(
                    Delivery.tenant_id == tenant_id,
                    Delivery.delivery_number == delivery_number,
                )
            )
            if existing:
                raise DeliveryDemoDomainError(f"Delivery number {delivery_number} already exists.")

            delivery_id = str(uuid4())
            delivery = Delivery(
                id=delivery_id,
                tenant_id=tenant_id,
                delivery_number=delivery_number,
                purchase_order_id=purchase_order_id,
                invoice_id=invoice_id,
                invoice_number=invoice_number,
                seller_business_id=seller_business_id,
                seller_gstin=seller_gstin,
                buyer_id=buyer_id,
                buyer_gstin=buyer_gstin,
                status="CREATED",
                ship_from=json.dumps(ship_from, sort_keys=True),
                ship_to=json.dumps(ship_to, sort_keys=True),
                currency=currency,
                declared_value=declared_value,
                version=1,
                created_by=actor,
                updated_by=actor,
            )
            db.add(delivery)

            for item in items_data:
                db.add(
                    DeliveryItem(
                        id=str(uuid4()),
                        delivery_id=delivery_id,
                        po_line_id=item["po_line_id"],
                        invoice_line_id=item.get("invoice_line_id"),
                        sku=item["sku"],
                        description=item["description"],
                        unit=item["unit"],
                        ordered_quantity=Decimal(str(item["ordered_quantity"])),
                        dispatched_quantity=Decimal("0.00"),
                        delivered_quantity=Decimal("0.00"),
                        accepted_quantity=Decimal("0.00"),
                        rejected_quantity=Decimal("0.00"),
                        supported_unit_value=Decimal(str(item["supported_unit_value"])),
                    )
                )

            # Record Event
            db.add(
                DeliveryEvent(
                    id=str(uuid4()),
                    delivery_id=delivery_id,
                    event_type="delivery.created",
                    actor=actor,
                    prior_status=None,
                    new_status="CREATED",
                    version=1,
                    correlation_id=correlation_id,
                )
            )

            self._audit(
                db, tenant_id, "delivery", delivery_id, 1, "delivery.created", "USER", actor,
                metadata={"delivery_number": delivery_number}, correlation_id=correlation_id
            )
            self._publish_event(
                db, tenant_id, "delivery", delivery_id, 1, "delivery.created",
                {"delivery_id": delivery_id, "status": "CREATED"}, correlation_id=correlation_id
            )

            return delivery

    async def mark_ready(
        self, tenant_id: str, delivery_id: str, actor: str, correlation_id: str | None = None
    ) -> Delivery:
        async with session() as db:
            delivery = await db.get(Delivery, delivery_id)
            if not delivery or delivery.tenant_id != tenant_id:
                raise DeliveryDemoDomainError("Delivery not found.")
            if delivery.status != "CREATED":
                raise DeliveryDemoDomainError(f"Cannot mark ready from status {delivery.status}.")

            delivery.status = "READY_TO_DISPATCH"
            delivery.version += 1
            delivery.updated_by = actor

            db.add(
                DeliveryEvent(
                    id=str(uuid4()),
                    delivery_id=delivery_id,
                    event_type="delivery.ready",
                    actor=actor,
                    prior_status="CREATED",
                    new_status="READY_TO_DISPATCH",
                    version=delivery.version,
                    correlation_id=correlation_id,
                )
            )

            self._audit(
                db, tenant_id, "delivery", delivery_id, delivery.version, "delivery.ready", "USER", actor,
                correlation_id=correlation_id
            )
            self._publish_event(
                db, tenant_id, "delivery", delivery_id, delivery.version, "delivery.ready",
                {"delivery_id": delivery_id, "status": "READY_TO_DISPATCH"}, correlation_id=correlation_id
            )

            return delivery

    async def dispatch_delivery(
        self,
        tenant_id: str,
        delivery_id: str,
        carrier_id: str,
        tracking_number: str,
        items_dispatch: dict[str, Decimal],  # sku -> dispatched_quantity
        actor: str,
        correlation_id: str | None = None,
    ) -> Delivery:
        async with session() as db:
            delivery = await db.get(Delivery, delivery_id)
            if not delivery or delivery.tenant_id != tenant_id:
                raise DeliveryDemoDomainError("Delivery not found.")
            if delivery.status not in ("CREATED", "READY_TO_DISPATCH"):
                raise DeliveryDemoDomainError(f"Cannot dispatch from status {delivery.status}.")

            items = (
                await db.scalars(
                    select(DeliveryItem).where(DeliveryItem.delivery_id == delivery_id)
                )
            ).all()

            if not items:
                raise DeliveryDemoDomainError("No items configured to dispatch.")

            for item in items:
                disp = items_dispatch.get(item.sku, item.ordered_quantity)
                if disp < 0:
                    raise DeliveryDemoDomainError("Dispatched quantity cannot be negative.")
                if disp > item.ordered_quantity:
                    raise DeliveryDemoDomainError(
                        f"Dispatched quantity ({disp}) for SKU {item.sku} exceeds ordered ({item.ordered_quantity})."
                    )
                item.dispatched_quantity = disp
                item.version += 1

            delivery.status = "DISPATCHED"
            delivery.carrier_id = carrier_id
            delivery.tracking_number = tracking_number
            delivery.dispatch_date = datetime.now(UTC)
            delivery.version += 1
            delivery.updated_by = actor

            db.add(
                DeliveryEvent(
                    id=str(uuid4()),
                    delivery_id=delivery_id,
                    event_type="delivery.dispatched",
                    actor=actor,
                    prior_status="READY_TO_DISPATCH",
                    new_status="DISPATCHED",
                    version=delivery.version,
                    correlation_id=correlation_id,
                )
            )

            self._audit(
                db, tenant_id, "delivery", delivery_id, delivery.version, "delivery.dispatched", "USER", actor,
                metadata={"carrier_id": carrier_id, "tracking_number": tracking_number},
                correlation_id=correlation_id
            )
            self._publish_event(
                db, tenant_id, "delivery", delivery_id, delivery.version, "delivery.dispatched",
                {"delivery_id": delivery_id, "status": "DISPATCHED"}, correlation_id=correlation_id
            )

            return delivery

    async def record_transit_event(
        self,
        tenant_id: str,
        delivery_id: str,
        event_type: str,  # delivery.event_recorded (pickup, transit, out-for-delivery)
        location: str,
        notes: str | None,
        actor: str,
        correlation_id: str | None = None,
    ) -> Delivery:
        # Supported event_type values map to status:
        # - pickup -> IN_TRANSIT
        # - transit -> IN_TRANSIT
        # - out-for-delivery -> OUT_FOR_DELIVERY
        new_status_map = {
            "pickup": "IN_TRANSIT",
            "transit": "IN_TRANSIT",
            "out-for-delivery": "OUT_FOR_DELIVERY",
        }
        sub_type = event_type.replace("delivery.transit_", "").replace("delivery.", "")
        new_status = new_status_map.get(sub_type, "IN_TRANSIT")

        async with session() as db:
            delivery = await db.get(Delivery, delivery_id)
            if not delivery or delivery.tenant_id != tenant_id:
                raise DeliveryDemoDomainError("Delivery not found.")
            if delivery.status not in ("DISPATCHED", "IN_TRANSIT", "OUT_FOR_DELIVERY"):
                raise DeliveryDemoDomainError(f"Cannot record transit event in status {delivery.status}.")

            prior = delivery.status
            delivery.status = new_status
            delivery.version += 1
            delivery.updated_by = actor

            db.add(
                DeliveryEvent(
                    id=str(uuid4()),
                    delivery_id=delivery_id,
                    event_type=f"delivery.{sub_type}",
                    actor=actor,
                    location=location,
                    notes=notes,
                    prior_status=prior,
                    new_status=new_status,
                    version=delivery.version,
                    correlation_id=correlation_id,
                )
            )

            self._audit(
                db, tenant_id, "delivery", delivery_id, delivery.version, f"delivery.{sub_type}", "USER", actor,
                metadata={"location": location, "notes": notes}, correlation_id=correlation_id
            )
            self._publish_event(
                db, tenant_id, "delivery", delivery_id, delivery.version, f"delivery.{sub_type}",
                {"delivery_id": delivery_id, "status": new_status, "location": location},
                correlation_id=correlation_id
            )

            return delivery

    async def record_delivery_attempt(
        self,
        tenant_id: str,
        delivery_id: str,
        success: bool,
        items_delivered: dict[str, Decimal],  # sku -> delivered_quantity
        failure_reason: str | None,
        actor: str,
        correlation_id: str | None = None,
    ) -> Delivery:
        async with session() as db:
            delivery = await db.get(Delivery, delivery_id)
            if not delivery or delivery.tenant_id != tenant_id:
                raise DeliveryDemoDomainError("Delivery not found.")
            if delivery.status not in ("IN_TRANSIT", "OUT_FOR_DELIVERY"):
                raise DeliveryDemoDomainError(f"Cannot record attempt from status {delivery.status}.")

            prior = delivery.status
            if success:
                items = (
                    await db.scalars(
                        select(DeliveryItem).where(DeliveryItem.delivery_id == delivery_id)
                    )
                ).all()

                all_matching = True
                for item in items:
                    deliv = items_delivered.get(item.sku, item.dispatched_quantity)
                    if deliv < 0:
                        raise DeliveryDemoDomainError("Delivered quantity cannot be negative.")
                    if deliv > item.dispatched_quantity:
                        raise DeliveryDemoDomainError(
                            f"Delivered quantity ({deliv}) for SKU {item.sku} exceeds dispatched ({item.dispatched_quantity})."
                        )
                    item.delivered_quantity = deliv
                    item.version += 1
                    if deliv < item.dispatched_quantity:
                        all_matching = False

                delivery.status = (
                    "DELIVERED_PENDING_ACCEPTANCE" if all_matching else "PARTIAL_PENDING_ACCEPTANCE"
                )
                delivery.delivered_at = datetime.now(UTC)
            else:
                delivery.status = "DELIVERY_FAILED"
                delivery.exception_code = failure_reason or "CARRIER_FAILURE"

            delivery.version += 1
            delivery.updated_by = actor

            db.add(
                DeliveryEvent(
                    id=str(uuid4()),
                    delivery_id=delivery_id,
                    event_type="delivery.delivery_attempted",
                    actor=actor,
                    notes=f"Success: {success}. Reason: {failure_reason}",
                    prior_status=prior,
                    new_status=delivery.status,
                    version=delivery.version,
                    correlation_id=correlation_id,
                )
            )

            self._audit(
                db, tenant_id, "delivery", delivery_id, delivery.version, "delivery.delivery_attempted", "USER", actor,
                metadata={"success": success, "status": delivery.status, "reason": failure_reason},
                correlation_id=correlation_id
            )
            self._publish_event(
                db, tenant_id, "delivery", delivery_id, delivery.version, "delivery.delivery_attempted",
                {"delivery_id": delivery_id, "status": delivery.status, "success": success},
                correlation_id=correlation_id
            )

            return delivery

    async def capture_pod(
        self,
        tenant_id: str,
        delivery_id: str,
        proof_type: str,
        restricted_object_key: str,
        mime_type: str,
        recipient_token: str | None,
        recipient_name: str | None,
        recipient_role: str | None,
        security_flags: list[str],
        actor: str,
        correlation_id: str | None = None,
    ) -> ProofOfDelivery:
        async with session() as db:
            delivery = await db.get(Delivery, delivery_id)
            if not delivery or delivery.tenant_id != tenant_id:
                raise DeliveryDemoDomainError("Delivery not found.")

            content_hash = hashlib.sha256(restricted_object_key.encode()).hexdigest()

            # Reject existing PENDING_VERIFICATION pods
            old_pods = (
                await db.scalars(
                    select(ProofOfDelivery).where(
                        ProofOfDelivery.delivery_id == delivery_id,
                        ProofOfDelivery.verification_status == "PENDING_VERIFICATION",
                    )
                )
            ).all()
            for old in old_pods:
                old.verification_status = "REJECTED"

            pod_id = str(uuid4())
            pod = ProofOfDelivery(
                id=pod_id,
                delivery_id=delivery_id,
                proof_type=proof_type,
                restricted_object_key=restricted_object_key,
                content_hash=content_hash,
                mime_type=mime_type,
                captured_at=datetime.now(UTC),
                recipient_token=recipient_token,
                recipient_name=recipient_name,
                recipient_role=recipient_role,
                verification_status="PENDING_VERIFICATION",
                security_flags=json.dumps(security_flags),
            )
            db.add(pod)

            # Record event
            db.add(
                DeliveryEvent(
                    id=str(uuid4()),
                    delivery_id=delivery_id,
                    event_type="delivery.pod_captured",
                    actor=actor,
                    notes=f"POD Captured: {proof_type} ({mime_type})",
                    prior_status=delivery.status,
                    new_status=delivery.status,
                    version=delivery.version,
                    correlation_id=correlation_id,
                )
            )

            self._audit(
                db, tenant_id, "proof", pod_id, 1, "delivery.pod_captured", "USER", actor,
                metadata={"delivery_id": delivery_id, "proof_type": proof_type},
                correlation_id=correlation_id
            )
            self._publish_event(
                db, tenant_id, "proof", pod_id, 1, "delivery.pod_captured",
                {"delivery_id": delivery_id, "pod_id": pod_id, "status": "PENDING_VERIFICATION"},
                correlation_id=correlation_id
            )

            return pod

    async def verify_pod(
        self,
        tenant_id: str,
        delivery_id: str,
        pod_id: str,
        verified: bool,
        rejection_reason: str | None,
        actor: str,
        correlation_id: str | None = None,
    ) -> ProofOfDelivery:
        async with session() as db:
            pod = await db.get(ProofOfDelivery, pod_id)
            if not pod or pod.delivery_id != delivery_id:
                raise DeliveryDemoDomainError("POD not found for target delivery.")
            delivery = await db.get(Delivery, delivery_id)
            if not delivery or delivery.tenant_id != tenant_id:
                raise DeliveryDemoDomainError("Delivery tenant scope mismatch.")

            evt_type = "delivery.pod_verified" if verified else "delivery.pod_rejected"
            pod.verification_status = "VERIFIED" if verified else "REJECTED"
            pod.verifier = actor
            pod.verification_method = "MANUAL_RECONCILIATION"

            if not verified and rejection_reason:
                flags = json.loads(pod.security_flags)
                flags.append(f"REJECTION_REASON: {rejection_reason}")
                pod.security_flags = json.dumps(flags)

            db.add(
                DeliveryEvent(
                    id=str(uuid4()),
                    delivery_id=delivery_id,
                    event_type=evt_type,
                    actor=actor,
                    notes=f"POD verification success={verified}. Reason={rejection_reason}",
                    prior_status=delivery.status,
                    new_status=delivery.status,
                    version=delivery.version,
                    correlation_id=correlation_id,
                )
            )

            self._audit(
                db, tenant_id, "proof", pod_id, 2, evt_type, "USER", actor,
                metadata={"verified": verified, "reason": rejection_reason},
                correlation_id=correlation_id
            )
            self._publish_event(
                db, tenant_id, "proof", pod_id, 2, evt_type,
                {"delivery_id": delivery_id, "pod_id": pod_id, "verified": verified},
                correlation_id=correlation_id
            )

            return pod

    async def record_buyer_acceptance(
        self,
        tenant_id: str,
        delivery_id: str,
        status: str,  # ACCEPTED, PARTIALLY_ACCEPTED, REJECTED
        items_acceptance: list[dict[str, Any]],  # sku, accepted_qty, rejected_qty, reason
        actor: str,
        correlation_id: str | None = None,
    ) -> BuyerAcceptance:
        if status not in ("ACCEPTED", "PARTIALLY_ACCEPTED", "REJECTED"):
            raise DeliveryDemoDomainError("Invalid buyer acceptance status.")

        async with session() as db:
            delivery = await db.get(Delivery, delivery_id)
            if not delivery or delivery.tenant_id != tenant_id:
                raise DeliveryDemoDomainError("Delivery not found.")
            if delivery.status not in (
                "DELIVERED_PENDING_ACCEPTANCE",
                "PARTIAL_PENDING_ACCEPTANCE",
                "IN_TRANSIT",
                "OUT_FOR_DELIVERY",
            ):
                raise DeliveryDemoDomainError(f"Cannot record buyer acceptance in status {delivery.status}.")

            items = (
                await db.scalars(
                    select(DeliveryItem).where(DeliveryItem.delivery_id == delivery_id)
                )
            ).all()

            accept_map = {item["sku"]: item for item in items_acceptance}

            verified_value = Decimal("0.00")
            for item in items:
                claim = accept_map.get(item.sku)
                if claim:
                    ac = Decimal(str(claim["accepted_qty"]))
                    rj = Decimal(str(claim["rejected_qty"]))
                else:
                    # Default: accept all delivered quantity
                    ac = item.delivered_quantity
                    rj = Decimal("0.00")

                if ac < 0 or rj < 0:
                    raise DeliveryDemoDomainError("Accepted/rejected quantities cannot be negative.")
                if (ac + rj) > item.delivered_quantity:
                    raise DeliveryDemoDomainError(
                        f"Sum of accepted ({ac}) and rejected ({rj}) for SKU {item.sku} exceeds delivered ({item.delivered_quantity})."
                    )

                item.accepted_quantity = ac
                item.rejected_quantity = rj
                if claim and claim.get("reason"):
                    item.rejection_reason = claim["reason"]
                item.version += 1

                # Supported line value = MIN(ordered_quantity, accepted_quantity) * supported_unit_value
                supported_qty = min(item.ordered_quantity, ac)
                verified_value += supported_qty * item.supported_unit_value

            delivery.verified_delivered_value = verified_value
            prior = delivery.status
            delivery.status = (
                "DELIVERED"
                if status == "ACCEPTED"
                else "PARTIALLY_ACCEPTED"
                if status == "PARTIALLY_ACCEPTED"
                else "REJECTED"
            )
            delivery.version += 1
            delivery.updated_by = actor

            # Create Buyer Acceptance record
            acc_id = str(uuid4())
            acceptance = BuyerAcceptance(
                id=acc_id,
                delivery_id=delivery_id,
                version=delivery.version,
                buyer_identity=delivery.buyer_id,
                status=status,
                accepted_value=verified_value,
                item_level_acceptance=json.dumps(items_acceptance),
                actor=actor,
                occurred_at=datetime.now(UTC),
            )
            db.add(acceptance)

            # Record event
            evt_type = (
                "delivery.accepted"
                if status == "ACCEPTED"
                else "delivery.partially_accepted"
                if status == "PARTIALLY_ACCEPTED"
                else "delivery.rejected"
            )
            db.add(
                DeliveryEvent(
                    id=str(uuid4()),
                    delivery_id=delivery_id,
                    event_type=evt_type,
                    actor=actor,
                    prior_status=prior,
                    new_status=delivery.status,
                    version=delivery.version,
                    correlation_id=correlation_id,
                )
            )

            self._audit(
                db, tenant_id, "delivery", delivery_id, delivery.version, evt_type, "USER", actor,
                metadata={"accepted_value": str(verified_value)}, correlation_id=correlation_id
            )
            self._publish_event(
                db, tenant_id, "delivery", delivery_id, delivery.version, evt_type,
                {"delivery_id": delivery_id, "status": delivery.status, "accepted_value": str(verified_value)},
                correlation_id=correlation_id
            )

            return acceptance

    async def cancel_delivery(
        self,
        tenant_id: str,
        delivery_id: str,
        reason: str,
        actor: str,
        correlation_id: str | None = None,
    ) -> Delivery:
        async with session() as db:
            delivery = await db.get(Delivery, delivery_id)
            if not delivery or delivery.tenant_id != tenant_id:
                raise DeliveryDemoDomainError("Delivery not found.")
            if delivery.status == "CANCELLED":
                return delivery

            # Cancellation after dispatch requires review / reason
            if delivery.status not in ("CREATED", "READY_TO_DISPATCH"):
                if not reason.strip():
                    raise DeliveryDemoDomainError("Cancellation after dispatch requires a reason.")

            prior = delivery.status
            delivery.status = "CANCELLED"
            delivery.version += 1
            delivery.updated_by = actor

            db.add(
                DeliveryEvent(
                    id=str(uuid4()),
                    delivery_id=delivery_id,
                    event_type="delivery.cancelled",
                    actor=actor,
                    notes=reason,
                    prior_status=prior,
                    new_status="CANCELLED",
                    version=delivery.version,
                    correlation_id=correlation_id,
                )
            )

            self._audit(
                db, tenant_id, "delivery", delivery_id, delivery.version, "delivery.cancelled", "USER", actor,
                metadata={"reason": reason}, correlation_id=correlation_id
            )
            self._publish_event(
                db, tenant_id, "delivery", delivery_id, delivery.version, "delivery.cancelled",
                {"delivery_id": delivery_id, "status": "CANCELLED", "reason": reason},
                correlation_id=correlation_id
            )

            return delivery

    async def propose_correction(
        self,
        tenant_id: str,
        delivery_id: str,
        correction_type: str,
        proposed_changes: dict[str, Any],
        reason: str,
        actor: str,
        correlation_id: str | None = None,
    ) -> DeliveryCorrection:
        async with session() as db:
            delivery = await db.get(Delivery, delivery_id)
            if not delivery or delivery.tenant_id != tenant_id:
                raise DeliveryDemoDomainError("Delivery not found.")

            correction_id = str(uuid4())
            correction = DeliveryCorrection(
                id=correction_id,
                delivery_id=delivery_id,
                aggregate_version=delivery.version,
                correction_type=correction_type,
                proposed_changes=json.dumps(proposed_changes),
                reason=reason,
                requester=actor,
                decision="PENDING",
                status="PENDING",
            )
            db.add(correction)

            self._audit(
                db, tenant_id, "correction", correction_id, 1, "delivery.corrected", "USER", actor,
                metadata={"delivery_id": delivery_id, "correction_type": correction_type},
                correlation_id=correlation_id
            )
            self._publish_event(
                db, tenant_id, "correction", correction_id, 1, "delivery.corrected",
                {"delivery_id": delivery_id, "correction_id": correction_id, "status": "PENDING"},
                correlation_id=correlation_id
            )

            return correction

    async def review_correction(
        self,
        tenant_id: str,
        correction_id: str,
        approve: bool,
        actor: str,
        correlation_id: str | None = None,
    ) -> DeliveryCorrection:
        async with session() as db:
            correction = await db.get(DeliveryCorrection, correction_id)
            if not correction:
                raise DeliveryDemoDomainError("Correction not found.")
            delivery = await db.get(Delivery, correction.delivery_id)
            if not delivery or delivery.tenant_id != tenant_id:
                raise DeliveryDemoDomainError("Delivery tenant scope mismatch.")

            if correction.decision != "PENDING":
                raise DeliveryDemoDomainError("Correction has already been reviewed.")

            correction.decision = "APPROVED" if approve else "REJECTED"
            correction.status = "APPROVED" if approve else "REJECTED"
            correction.reviewer = actor

            if approve:
                # Apply proposed changes
                changes = json.loads(correction.proposed_changes)
                if "expected_delivery_date" in changes:
                    delivery.expected_delivery_date = date.fromisoformat(changes["expected_delivery_date"])
                if "declared_value" in changes:
                    delivery.declared_value = Decimal(str(changes["declared_value"]))
                if "tracking_number" in changes:
                    delivery.tracking_number = changes["tracking_number"]
                if "items" in changes:
                    # Update item ordered quantities if creation corrections
                    items = (
                        await db.scalars(
                            select(DeliveryItem).where(DeliveryItem.delivery_id == delivery.id)
                        )
                    ).all()
                    item_map = {item.sku: item for item in items}
                    for ch_item in changes["items"]:
                        sku = ch_item["sku"]
                        if sku in item_map:
                            if "ordered_quantity" in ch_item:
                                item_map[sku].ordered_quantity = Decimal(str(ch_item["ordered_quantity"]))
                            if "supported_unit_value" in ch_item:
                                item_map[sku].supported_unit_value = Decimal(str(ch_item["supported_unit_value"]))

                delivery.version += 1
                delivery.updated_by = actor
                correction.applied_version = delivery.version

                db.add(
                    DeliveryEvent(
                        id=str(uuid4()),
                        delivery_id=delivery.id,
                        event_type="delivery.corrected",
                        actor=actor,
                        notes=f"Correction approved: {correction.reason}",
                        prior_status=delivery.status,
                        new_status=delivery.status,
                        version=delivery.version,
                        correlation_id=correlation_id,
                    )
                )

            self._audit(
                db, tenant_id, "correction", correction_id, 2,
                f"delivery.correction_{correction.decision.lower()}", "USER", actor,
                metadata={"delivery_id": delivery.id}, correlation_id=correlation_id
            )
            self._publish_event(
                db, tenant_id, "correction", correction_id, 2,
                f"delivery.correction_{correction.decision.lower()}",
                {"delivery_id": delivery.id, "correction_id": correction_id, "status": correction.decision},
                correlation_id=correlation_id
            )

            return correction

    # --- Search & Read Operations ---

    async def get_delivery(self, tenant_id: str, delivery_id: str) -> dict[str, Any]:
        async with session() as db:
            delivery = await db.get(Delivery, delivery_id)
            if not delivery or delivery.tenant_id != tenant_id:
                raise DeliveryDemoDomainError("Delivery not found.")

            items = (
                await db.scalars(
                    select(DeliveryItem).where(DeliveryItem.delivery_id == delivery_id)
                )
            ).all()

            events = (
                await db.scalars(
                    select(DeliveryEvent)
                    .where(DeliveryEvent.delivery_id == delivery_id)
                    .order_by(DeliveryEvent.occurred_at.asc())
                )
            ).all()

            pods = (
                await db.scalars(
                    select(ProofOfDelivery)
                    .where(ProofOfDelivery.delivery_id == delivery_id)
                    .order_by(ProofOfDelivery.captured_at.desc())
                )
            ).all()

            acceptances = (
                await db.scalars(
                    select(BuyerAcceptance)
                    .where(BuyerAcceptance.delivery_id == delivery_id)
                    .order_by(BuyerAcceptance.occurred_at.desc())
                )
            ).all()

            corrections = (
                await db.scalars(
                    select(DeliveryCorrection)
                    .where(DeliveryCorrection.delivery_id == delivery_id)
                    .order_by(DeliveryCorrection.aggregate_version.desc())
                )
            ).all()

            return {
                "delivery": delivery,
                "items": items,
                "events": events,
                "proofs": pods,
                "acceptances": acceptances,
                "corrections": corrections,
            }


delivery_service = DeliveryDemoService()
