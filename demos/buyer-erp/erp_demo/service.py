import hashlib
import hmac
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import session
from .models import (
    AuditEvent,
    Counterparty,
    GoodsServiceReceipt,
    InboxEvent,
    InvoiceAcceptance,
    InvoiceMatch,
    OutboxEvent,
    PurchaseOrder,
    PurchaseOrderLine,
    ReceiptLine,
    SupplierInvoice,
)
from .schemas import (
    AcceptanceCreate,
    DisputeCreate,
    GSTEventEnvelope,
    GSTInvoiceSnapshot,
    PurchaseOrderCreate,
    ReceiptCreate,
)
from .settings import get_settings


class ERPDomainError(RuntimeError):
    pass


class ERPNotFoundError(ERPDomainError):
    pass


class ERPConflictError(ERPDomainError):
    pass


class ERPService:
    async def dashboard(self, tenant_id: str) -> dict[str, Any]:
        async with session() as db:
            counterparties = (
                await db.scalars(
                    select(Counterparty)
                    .where(Counterparty.tenant_id == tenant_id)
                    .order_by(Counterparty.legal_name)
                )
            ).all()
            orders = (
                await db.scalars(
                    select(PurchaseOrder)
                    .where(PurchaseOrder.tenant_id == tenant_id)
                    .order_by(PurchaseOrder.order_date.desc())
                )
            ).all()
            receipts = (
                await db.scalars(
                    select(GoodsServiceReceipt)
                    .where(GoodsServiceReceipt.tenant_id == tenant_id)
                    .order_by(GoodsServiceReceipt.posting_date.desc())
                )
            ).all()
            invoices = (
                await db.scalars(
                    select(SupplierInvoice)
                    .where(SupplierInvoice.tenant_id == tenant_id)
                    .order_by(SupplierInvoice.invoice_date.desc())
                )
            ).all()
            matches = (
                await db.scalars(
                    select(InvoiceMatch)
                    .where(InvoiceMatch.tenant_id == tenant_id)
                    .order_by(InvoiceMatch.updated_at.desc())
                )
            ).all()
            acceptances = (
                await db.scalars(
                    select(InvoiceAcceptance).where(InvoiceAcceptance.tenant_id == tenant_id)
                )
            ).all()
            audits = (
                await db.scalars(
                    select(AuditEvent)
                    .where(AuditEvent.tenant_id == tenant_id)
                    .order_by(AuditEvent.occurred_at.desc())
                    .limit(30)
                )
            ).all()
            outbox_pending = await db.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.tenant_id == tenant_id, OutboxEvent.published_at.is_(None))
            )

        invoice_by_id = {value.id: value for value in invoices}
        acceptance_by_match = {value.match_id: value for value in acceptances}
        return {
            "environment": "SYNTHETIC_NON_PRODUCTION",
            "tenant_id": tenant_id,
            "summary": {
                "open_purchase_orders": sum(
                    value.status not in {"CLOSED", "CANCELLED", "REJECTED"} for value in orders
                ),
                "ordered_value": str(sum((value.total for value in orders), Decimal("0"))),
                "posted_receipt_value": str(
                    sum(
                        (value.accepted_value for value in receipts if value.status == "POSTED"),
                        Decimal("0"),
                    )
                ),
                "supported_invoice_value": str(
                    sum((value.supported_value for value in matches), Decimal("0"))
                ),
                "exceptions": sum(
                    value.status in {"MISMATCHED", "DISPUTED", "REVIEW_REQUIRED"}
                    for value in matches
                ),
                "pending_outbox_events": outbox_pending or 0,
            },
            "counterparties": [self._counterparty_projection(value) for value in counterparties],
            "purchase_orders": [self._po_projection(value) for value in orders],
            "receipts": [self._receipt_projection(value) for value in receipts],
            "invoice_matches": [
                self._match_projection(
                    value,
                    invoice_by_id[value.invoice_id],
                    acceptance_by_match.get(value.id),
                )
                for value in matches
            ],
            "audit_events": [self._audit_projection(value) for value in audits],
        }

    async def create_purchase_order(
        self, tenant_id: str, body: PurchaseOrderCreate, actor: str, correlation_id: str
    ) -> dict[str, Any]:
        async with session() as db:
            existing = await db.scalar(
                select(PurchaseOrder).where(
                    PurchaseOrder.tenant_id == tenant_id,
                    PurchaseOrder.po_number == body.po_number,
                )
            )
            if existing is not None:
                raise ERPConflictError("Purchase order number already exists in this tenant.")
            buyer = await self._counterparty(db, tenant_id, body.buyer_id)
            supplier = await self._counterparty(db, tenant_id, body.supplier_business_id)
            if buyer.role != "BUYER" or buyer.relationship_status != "APPROVED":
                raise ERPDomainError("The buyer relationship is not approved.")
            if supplier.role != "SUPPLIER" or supplier.relationship_status != "APPROVED":
                raise ERPDomainError("The supplier relationship is not approved.")
            subtotal = sum(
                (line.quantity * line.unit_price for line in body.lines), Decimal("0")
            ).quantize(Decimal("0.01"))
            tax = sum(
                (
                    line.quantity
                    * line.unit_price
                    * line.tax_rate
                    / Decimal("100")
                    for line in body.lines
                ),
                Decimal("0"),
            ).quantize(Decimal("0.01"))
            order = PurchaseOrder(
                id=f"po_demo_{uuid4().hex[:16]}",
                tenant_id=tenant_id,
                po_number=body.po_number,
                buyer_id=body.buyer_id,
                supplier_business_id=body.supplier_business_id,
                buyer_gstin=buyer.gstin,
                seller_gstin=supplier.gstin,
                order_date=body.order_date,
                expected_delivery_date=body.expected_delivery_date,
                currency=body.currency,
                subtotal=subtotal,
                tax=tax,
                total=subtotal + tax,
                payment_terms_days=body.payment_terms_days,
                status="DRAFT",
            )
            db.add(order)
            await db.flush()
            for index, line in enumerate(body.lines, start=1):
                db.add(
                    PurchaseOrderLine(
                        id=f"pol_demo_{uuid4().hex[:16]}",
                        purchase_order_id=order.id,
                        line_number=index,
                        sku=line.sku,
                        description=line.description,
                        quantity=line.quantity,
                        unit=line.unit,
                        unit_price=line.unit_price,
                        tax_rate=line.tax_rate,
                        line_total=(line.quantity * line.unit_price).quantize(
                            Decimal("0.01")
                        ),
                        received_quantity=Decimal("0"),
                        accepted_quantity=Decimal("0"),
                    )
                )
            self._record(
                db,
                order,
                "purchase_order.created",
                actor,
                correlation_id,
                {"po_number": order.po_number, "total": str(order.total)},
            )
            return self._po_projection(order)

    async def transition_purchase_order(
        self,
        tenant_id: str,
        order_id: str,
        action: str,
        expected_version: int,
        actor: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        transitions = {
            ("DRAFT", "submit"): "SUBMITTED",
            ("SUBMITTED", "approve"): "APPROVED",
            ("SUBMITTED", "reject"): "REJECTED",
            ("APPROVED", "cancel"): "CANCELLED",
            ("PARTIALLY_FULFILLED", "cancel"): "CANCELLED",
        }
        async with session() as db:
            order = await self._purchase_order(db, tenant_id, order_id, lock=True)
            if order.version != expected_version:
                raise ERPConflictError(
                    f"Version conflict: current purchase-order version is {order.version}."
                )
            new_status = transitions.get((order.status, action))
            if new_status is None:
                raise ERPDomainError(f"Cannot {action} a purchase order in {order.status} state.")
            order.status = new_status
            order.version += 1
            if new_status == "APPROVED":
                order.approved_at = datetime.now(UTC)
                order.approved_by = actor
            self._record(
                db,
                order,
                f"purchase_order.{new_status.lower()}",
                actor,
                correlation_id,
                {"status": new_status},
            )
            return self._po_projection(order)

    async def create_receipt(
        self, tenant_id: str, body: ReceiptCreate, actor: str, correlation_id: str
    ) -> dict[str, Any]:
        async with session() as db:
            order = await self._purchase_order(db, tenant_id, body.purchase_order_id)
            if order.status not in {"APPROVED", "PARTIALLY_FULFILLED"}:
                raise ERPDomainError("Receipts require an approved, unfulfilled purchase order.")
            existing = await db.scalar(
                select(GoodsServiceReceipt).where(
                    GoodsServiceReceipt.tenant_id == tenant_id,
                    GoodsServiceReceipt.receipt_number == body.receipt_number,
                )
            )
            if existing is not None:
                raise ERPConflictError("Receipt number already exists in this tenant.")
            order_lines = {
                value.id: value
                for value in (
                    await db.scalars(
                        select(PurchaseOrderLine).where(
                            PurchaseOrderLine.purchase_order_id == order.id
                        )
                    )
                ).all()
            }
            accepted_value = Decimal("0")
            rejected_value = Decimal("0")
            receipt_line_values: list[tuple[Any, Decimal]] = []
            for requested in body.lines:
                line = order_lines.get(requested.purchase_order_line_id)
                if line is None:
                    raise ERPDomainError("A receipt line does not belong to the purchase order.")
                if requested.accepted_quantity + requested.rejected_quantity != requested.received_quantity:
                    raise ERPDomainError(
                        "Accepted and rejected quantity must equal received quantity."
                    )
                remaining = line.quantity - line.received_quantity
                if requested.received_quantity > remaining:
                    raise ERPDomainError("Receipt quantity exceeds the unreceived order quantity.")
                line_value = (
                    requested.accepted_quantity
                    * line.unit_price
                    * (Decimal("1") + line.tax_rate / Decimal("100"))
                ).quantize(Decimal("0.01"))
                rejected_line_value = (
                    requested.rejected_quantity
                    * line.unit_price
                    * (Decimal("1") + line.tax_rate / Decimal("100"))
                ).quantize(Decimal("0.01"))
                accepted_value += line_value
                rejected_value += rejected_line_value
                receipt_line_values.append((requested, line_value))
            receipt = GoodsServiceReceipt(
                id=f"rcpt_demo_{uuid4().hex[:16]}",
                tenant_id=tenant_id,
                receipt_number=body.receipt_number,
                purchase_order_id=order.id,
                delivery_reference=body.delivery_reference,
                receipt_type=body.receipt_type,
                posting_date=body.posting_date,
                receiver_token=body.receiver_token,
                status="DRAFT",
                accepted_value=accepted_value,
                rejected_value=rejected_value,
                source_hash=self._hash(body.model_dump(mode="json")),
            )
            db.add(receipt)
            await db.flush()
            for requested, line_value in receipt_line_values:
                db.add(
                    ReceiptLine(
                        id=f"rcl_demo_{uuid4().hex[:16]}",
                        receipt_id=receipt.id,
                        purchase_order_line_id=requested.purchase_order_line_id,
                        received_quantity=requested.received_quantity,
                        accepted_quantity=requested.accepted_quantity,
                        rejected_quantity=requested.rejected_quantity,
                        accepted_value=line_value,
                        discrepancy=requested.discrepancy,
                    )
                )
            self._record(
                db,
                receipt,
                "receipt.created",
                actor,
                correlation_id,
                {"receipt_number": receipt.receipt_number},
            )
            return self._receipt_projection(receipt)

    async def post_receipt(
        self,
        tenant_id: str,
        receipt_id: str,
        expected_version: int,
        actor: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        async with session() as db:
            receipt = await self._receipt(db, tenant_id, receipt_id, lock=True)
            if receipt.version != expected_version:
                raise ERPConflictError(
                    f"Version conflict: current receipt version is {receipt.version}."
                )
            if receipt.status != "DRAFT":
                raise ERPDomainError("Only a draft receipt can be posted.")
            order = await self._purchase_order(
                db, tenant_id, receipt.purchase_order_id, lock=True
            )
            lines = (
                await db.scalars(
                    select(ReceiptLine).where(ReceiptLine.receipt_id == receipt.id)
                )
            ).all()
            for value in lines:
                order_line = await db.get(PurchaseOrderLine, value.purchase_order_line_id)
                if order_line is None:
                    raise ERPDomainError("The purchase-order line no longer exists.")
                order_line.received_quantity += value.received_quantity
                order_line.accepted_quantity += value.accepted_quantity
            receipt.status = "POSTED"
            receipt.version += 1
            all_order_lines = (
                await db.scalars(
                    select(PurchaseOrderLine).where(
                        PurchaseOrderLine.purchase_order_id == order.id
                    )
                )
            ).all()
            order.status = (
                "FULFILLED"
                if all(line.accepted_quantity >= line.quantity for line in all_order_lines)
                else "PARTIALLY_FULFILLED"
            )
            order.version += 1
            self._record(
                db,
                receipt,
                "receipt.posted",
                actor,
                correlation_id,
                {"accepted_value": str(receipt.accepted_value)},
            )
            self._record(
                db,
                order,
                f"purchase_order.{order.status.lower()}",
                actor,
                correlation_id,
                {"receipt_id": receipt.id},
            )
            invoices = (
                await db.scalars(
                    select(SupplierInvoice).where(
                        SupplierInvoice.tenant_id == tenant_id,
                        SupplierInvoice.purchase_order_id == order.id,
                    )
                )
            ).all()
            for invoice in invoices:
                await self._recalculate_match(db, tenant_id, invoice, actor, correlation_id)
            return self._receipt_projection(receipt)

    async def recalculate_match(
        self, tenant_id: str, invoice_id: str, actor: str, correlation_id: str
    ) -> dict[str, Any]:
        async with session() as db:
            invoice = await self._invoice(db, tenant_id, invoice_id)
            match = await self._recalculate_match(
                db, tenant_id, invoice, actor, correlation_id
            )
            acceptance = await db.scalar(
                select(InvoiceAcceptance).where(InvoiceAcceptance.match_id == match.id)
            )
            return self._match_projection(match, invoice, acceptance)

    async def accept_match(
        self,
        tenant_id: str,
        match_id: str,
        expected_version: int,
        body: AcceptanceCreate,
        correlation_id: str,
    ) -> dict[str, Any]:
        async with session() as db:
            match = await self._match(db, tenant_id, match_id, lock=True)
            if match.version != expected_version:
                raise ERPConflictError(
                    f"Version conflict: current match version is {match.version}."
                )
            if match.status not in {"MATCHED", "PARTIAL_MATCH"}:
                raise ERPDomainError("Only a matched or partial match can be accepted.")
            if body.accepted_amount > match.supported_value:
                raise ERPDomainError("Accepted amount exceeds the deterministically supported value.")
            if await db.scalar(
                select(InvoiceAcceptance).where(InvoiceAcceptance.match_id == match.id)
            ):
                raise ERPConflictError("This invoice match already has an acceptance record.")
            status = (
                "ACCEPTED"
                if body.accepted_amount == match.invoice_value
                else "PARTIALLY_ACCEPTED"
            )
            match.status = status
            match.reviewed_by = body.actor
            match.version += 1
            acceptance = InvoiceAcceptance(
                id=f"accept_demo_{uuid4().hex[:16]}",
                tenant_id=tenant_id,
                match_id=match.id,
                accepted_amount=body.accepted_amount,
                status=status,
                reason=body.reason,
                actor=body.actor,
                accepted_at=datetime.now(UTC),
                match_version=match.version,
            )
            db.add(acceptance)
            invoice = await self._invoice(db, tenant_id, match.invoice_id)
            invoice.matching_status = status
            self._record(
                db,
                match,
                "invoice_match.accepted",
                body.actor,
                correlation_id,
                {"accepted_amount": str(body.accepted_amount), "status": status},
            )
            return self._match_projection(match, invoice, acceptance)

    async def dispute_match(
        self,
        tenant_id: str,
        match_id: str,
        expected_version: int,
        body: DisputeCreate,
        correlation_id: str,
    ) -> dict[str, Any]:
        async with session() as db:
            match = await self._match(db, tenant_id, match_id, lock=True)
            if match.version != expected_version:
                raise ERPConflictError(
                    f"Version conflict: current match version is {match.version}."
                )
            if match.status in {"ACCEPTED", "PARTIALLY_ACCEPTED"}:
                raise ERPDomainError("An accepted match requires a reviewer correction workflow.")
            match.status = "DISPUTED"
            match.reviewed_by = body.actor
            match.discrepancies = [*match.discrepancies, f"DISPUTE: {body.reason}"]
            match.version += 1
            invoice = await self._invoice(db, tenant_id, match.invoice_id)
            invoice.matching_status = "DISPUTED"
            self._record(
                db,
                match,
                "invoice_match.disputed",
                body.actor,
                correlation_id,
                {"reason": body.reason},
            )
            return self._match_projection(match, invoice, None)

    async def consume_gst_event(
        self,
        event: GSTEventEnvelope,
        signed_payload_hash: str | None = None,
    ) -> dict[str, Any]:
        canonical = event.model_dump(mode="json", exclude={"signature"})
        payload_hash = signed_payload_hash or self._hash(canonical)
        async with session() as db:
            existing = await db.scalar(
                select(InboxEvent).where(
                    InboxEvent.source_application == event.source_application,
                    InboxEvent.event_id == event.event_id,
                )
            )
            if existing is not None:
                return {"status": "DUPLICATE_IGNORED", "event_id": event.event_id}
            inbox = InboxEvent(
                id=str(uuid4()),
                source_application=event.source_application,
                event_id=event.event_id,
                event_type=event.event_type,
                tenant_id=event.tenant_id,
                status="RECEIVED",
                payload_hash=payload_hash,
            )
            db.add(inbox)
            invoice = await db.get(SupplierInvoice, event.aggregate.id)
            snapshot_document = event.data.get("invoice_snapshot")
            snapshot = (
                GSTInvoiceSnapshot.model_validate(snapshot_document)
                if isinstance(snapshot_document, dict)
                else None
            )
            if snapshot is not None and snapshot.id != event.aggregate.id:
                inbox.status = "FAILED"
                inbox.last_error = "GST invoice snapshot does not match the event aggregate."
                return {
                    "status": "SNAPSHOT_AGGREGATE_MISMATCH",
                    "event_id": event.event_id,
                }
            invoice_created = False
            if invoice is None or invoice.tenant_id != event.tenant_id:
                if snapshot is None or snapshot.tenant_id != event.tenant_id:
                    inbox.status = "FAILED"
                    inbox.last_error = (
                        "Invoice detail is not present. Fetch the authoritative GST invoice snapshot "
                        "through the configured service API before processing this event."
                    )
                    return {
                        "status": "DETAIL_FETCH_REQUIRED",
                        "event_id": event.event_id,
                        "invoice_id": event.aggregate.id,
                    }
                invoice = SupplierInvoice(
                    id=snapshot.id,
                    tenant_id=snapshot.tenant_id,
                    invoice_number=snapshot.invoice_number,
                    seller_gstin=snapshot.seller_gstin,
                    buyer_gstin=snapshot.buyer_gstin,
                    purchase_order_id=snapshot.purchase_order_id,
                    invoice_date=snapshot.invoice_date,
                    currency=snapshot.currency,
                    claimed_total=snapshot.total_invoice_value,
                    gst_status=snapshot.status,
                    irn_token=snapshot.irn,
                    source_version=snapshot.version,
                    source_hash=snapshot.source_document_hash,
                    matching_status="PENDING",
                )
                db.add(invoice)
                await db.flush()
                invoice_created = True
            if not invoice_created and event.aggregate.version <= invoice.source_version:
                inbox.status = "PROCESSED"
                inbox.processed_at = datetime.now(UTC)
                return {"status": "STALE_VERSION_IGNORED", "event_id": event.event_id}

            if snapshot is not None:
                invoice.invoice_number = snapshot.invoice_number
                invoice.seller_gstin = snapshot.seller_gstin
                invoice.buyer_gstin = snapshot.buyer_gstin
                invoice.purchase_order_id = snapshot.purchase_order_id
                invoice.invoice_date = snapshot.invoice_date
                invoice.currency = snapshot.currency
                invoice.claimed_total = snapshot.total_invoice_value
                invoice.irn_token = snapshot.irn
            invoice.source_version = event.aggregate.version
            invoice.gst_status = (
                "CANCELLED" if event.event_type == "invoice.cancelled" else "REGISTERED"
            )
            invoice.source_hash = str(event.data.get("source_hash") or payload_hash)
            if event.data.get("irn_token"):
                invoice.irn_token = str(event.data["irn_token"])
            match = await db.scalar(
                select(InvoiceMatch).where(InvoiceMatch.invoice_id == invoice.id)
            )
            if event.event_type == "invoice.cancelled" and match is not None:
                match.status = "REVIEW_REQUIRED"
                match.discrepancies = [
                    *match.discrepancies,
                    "GST_INVOICE_CANCELLED_AFTER_MATCH",
                ]
                match.version += 1
                invoice.matching_status = "REVIEW_REQUIRED"
                self._record(
                    db,
                    match,
                    "invoice_match.review_required",
                    event.source_application,
                    event.correlation_id,
                    {"reason": "GST_INVOICE_CANCELLED", "gst_event_id": event.event_id},
                    actor_type="SERVICE",
                )
            elif (
                event.event_type == "invoice.registered"
                and match is not None
                and match.status in {"ACCEPTED", "PARTIALLY_ACCEPTED"}
            ):
                match.status = "REVIEW_REQUIRED"
                if "GST_INVOICE_VERSION_CHANGED_AFTER_ACCEPTANCE" not in match.discrepancies:
                    match.discrepancies = [
                        *match.discrepancies,
                        "GST_INVOICE_VERSION_CHANGED_AFTER_ACCEPTANCE",
                    ]
                match.version += 1
                invoice.matching_status = "REVIEW_REQUIRED"
                self._record(
                    db,
                    match,
                    "invoice_match.review_required",
                    event.source_application,
                    event.correlation_id,
                    {
                        "reason": "GST_INVOICE_VERSION_CHANGED_AFTER_ACCEPTANCE",
                        "gst_event_id": event.event_id,
                    },
                    actor_type="SERVICE",
                )
            elif event.event_type == "invoice.registered":
                await self._recalculate_match(
                    db,
                    event.tenant_id,
                    invoice,
                    event.source_application,
                    event.correlation_id,
                )
            inbox.status = "PROCESSED"
            inbox.processed_at = datetime.now(UTC)
            return {
                "status": "PROCESSED",
                "event_id": event.event_id,
                "invoice_id": invoice.id,
                "gst_status": invoice.gst_status,
            }

    async def verify_counterparty(
        self, tenant_id: str, business_id_or_gstin: str
    ) -> dict[str, Any]:
        async with session() as db:
            value = await db.scalar(
                select(Counterparty).where(
                    Counterparty.tenant_id == tenant_id,
                    or_(
                        Counterparty.business_id == business_id_or_gstin,
                        Counterparty.gstin == business_id_or_gstin,
                    ),
                )
            )
            if value is None:
                raise ERPNotFoundError("Counterparty was not found in the signed tenant scope.")
            return self._counterparty_projection(value)

    async def get_purchase_order(self, tenant_id: str, order_id: str) -> dict[str, Any]:
        async with session() as db:
            order = await self._purchase_order(db, tenant_id, order_id)
            lines = (
                await db.scalars(
                    select(PurchaseOrderLine)
                    .where(PurchaseOrderLine.purchase_order_id == order.id)
                    .order_by(PurchaseOrderLine.line_number)
                )
            ).all()
            return {
                **self._po_projection(order),
                "lines": [self._po_line_projection(value) for value in lines],
            }

    async def find_purchase_order_by_invoice(
        self, tenant_id: str, invoice_id_or_number: str
    ) -> dict[str, Any]:
        async with session() as db:
            invoice = await db.scalar(
                select(SupplierInvoice).where(
                    SupplierInvoice.tenant_id == tenant_id,
                    or_(
                        SupplierInvoice.id == invoice_id_or_number,
                        SupplierInvoice.invoice_number == invoice_id_or_number,
                    ),
                )
            )
            if invoice is None:
                raise ERPNotFoundError("Supplier invoice was not found in the signed tenant scope.")
            if not invoice.purchase_order_id:
                return {
                    "invoice_id": invoice.id,
                    "invoice_number": invoice.invoice_number,
                    "purchase_order": None,
                    "match_reason": "PURCHASE_ORDER_REFERENCE_MISSING",
                }
            order = await self._purchase_order(db, tenant_id, invoice.purchase_order_id)
            return {
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "purchase_order": self._po_projection(order),
                "match_reason": "EXPLICIT_PURCHASE_ORDER_REFERENCE",
            }

    async def get_receipt(self, tenant_id: str, receipt_id: str) -> dict[str, Any]:
        async with session() as db:
            receipt = await self._receipt(db, tenant_id, receipt_id)
            lines = (
                await db.scalars(
                    select(ReceiptLine).where(ReceiptLine.receipt_id == receipt.id)
                )
            ).all()
            return {
                **self._receipt_projection(receipt),
                "lines": [self._receipt_line_projection(value) for value in lines],
            }

    async def get_invoice_match(self, tenant_id: str, match_id: str) -> dict[str, Any]:
        async with session() as db:
            match = await self._match(db, tenant_id, match_id)
            invoice = await self._invoice(db, tenant_id, match.invoice_id)
            acceptance = await db.scalar(
                select(InvoiceAcceptance).where(InvoiceAcceptance.match_id == match.id)
            )
            return self._match_projection(match, invoice, acceptance)

    async def get_invoice_acceptance(
        self, tenant_id: str, match_id_or_invoice_id: str
    ) -> dict[str, Any]:
        async with session() as db:
            match = await db.scalar(
                select(InvoiceMatch).where(
                    InvoiceMatch.tenant_id == tenant_id,
                    or_(
                        InvoiceMatch.id == match_id_or_invoice_id,
                        InvoiceMatch.invoice_id == match_id_or_invoice_id,
                    ),
                )
            )
            if match is None:
                raise ERPNotFoundError("Invoice match was not found in the signed tenant scope.")
            acceptance = await db.scalar(
                select(InvoiceAcceptance).where(InvoiceAcceptance.match_id == match.id)
            )
            return {
                "match_id": match.id,
                "invoice_id": match.invoice_id,
                "match_status": match.status,
                "supported_value": str(match.supported_value),
                "acceptance": self._acceptance_projection(acceptance)
                if acceptance
                else None,
            }

    async def _recalculate_match(
        self,
        db: AsyncSession,
        tenant_id: str,
        invoice: SupplierInvoice,
        actor: str,
        correlation_id: str,
    ) -> InvoiceMatch:
        match = await db.scalar(
            select(InvoiceMatch)
            .where(InvoiceMatch.invoice_id == invoice.id)
            .with_for_update()
        )
        if match is not None and match.status in {"ACCEPTED", "PARTIALLY_ACCEPTED"}:
            raise ERPDomainError("An accepted match requires the reviewer correction workflow.")
        discrepancies: list[str] = []
        order: PurchaseOrder | None = None
        receipts: list[GoodsServiceReceipt] = []
        if invoice.purchase_order_id:
            order = await db.scalar(
                select(PurchaseOrder).where(
                    PurchaseOrder.id == invoice.purchase_order_id,
                    PurchaseOrder.tenant_id == tenant_id,
                )
            )
        if order is None:
            discrepancies.append("PURCHASE_ORDER_NOT_FOUND")
        else:
            if order.seller_gstin != invoice.seller_gstin:
                discrepancies.append("SELLER_GSTIN_MISMATCH")
            if order.buyer_gstin != invoice.buyer_gstin:
                discrepancies.append("BUYER_GSTIN_MISMATCH")
            if order.status in {"CANCELLED", "REJECTED"}:
                discrepancies.append("PURCHASE_ORDER_NOT_ACTIVE")
            receipts = list(
                (
                    await db.scalars(
                        select(GoodsServiceReceipt).where(
                            GoodsServiceReceipt.tenant_id == tenant_id,
                            GoodsServiceReceipt.purchase_order_id == order.id,
                            GoodsServiceReceipt.status == "POSTED",
                        )
                    )
                ).all()
            )
            if not receipts:
                discrepancies.append("POSTED_RECEIPT_NOT_FOUND")
        if invoice.gst_status != "REGISTERED":
            discrepancies.append("GST_INVOICE_NOT_ACTIVE")
        po_value = order.total if order else Decimal("0")
        receipt_value = sum(
            (value.accepted_value for value in receipts), Decimal("0")
        )
        supported = min(invoice.claimed_total, po_value, receipt_value)
        identity_errors = {
            "PURCHASE_ORDER_NOT_FOUND",
            "SELLER_GSTIN_MISMATCH",
            "BUYER_GSTIN_MISMATCH",
            "PURCHASE_ORDER_NOT_ACTIVE",
            "POSTED_RECEIPT_NOT_FOUND",
            "GST_INVOICE_NOT_ACTIVE",
        }
        if identity_errors.intersection(discrepancies):
            status = "MISMATCHED"
        elif supported < invoice.claimed_total:
            status = "PARTIAL_MATCH"
            discrepancies.append("PARTIAL_RECEIPT_OR_ORDER_VALUE")
        else:
            status = "MATCHED"
        if match is None:
            match = InvoiceMatch(
                id=f"match_demo_{uuid4().hex[:16]}",
                tenant_id=tenant_id,
                invoice_id=invoice.id,
                purchase_order_id=order.id if order else None,
                receipt_id=receipts[-1].id if receipts else None,
                po_value=po_value,
                receipt_value=receipt_value,
                invoice_value=invoice.claimed_total,
                supported_value=supported,
                tolerance_amount=Decimal("1.00"),
                discrepancies=discrepancies,
                status=status,
            )
            db.add(match)
            await db.flush()
        else:
            match.purchase_order_id = order.id if order else None
            match.receipt_id = receipts[-1].id if receipts else None
            match.po_value = po_value
            match.receipt_value = receipt_value
            match.invoice_value = invoice.claimed_total
            match.supported_value = supported
            match.discrepancies = discrepancies
            match.status = status
            match.version += 1
        invoice.matching_status = status
        self._record(
            db,
            match,
            "invoice_match.recalculated",
            actor,
            correlation_id,
            {"status": status, "supported_value": str(supported)},
        )
        return match

    @staticmethod
    async def _counterparty(
        db: AsyncSession, tenant_id: str, business_id: str
    ) -> Counterparty:
        value = await db.scalar(
            select(Counterparty).where(
                Counterparty.tenant_id == tenant_id,
                Counterparty.business_id == business_id,
            )
        )
        if value is None:
            raise ERPNotFoundError("Counterparty was not found in this tenant.")
        return value

    @staticmethod
    async def _purchase_order(
        db: AsyncSession, tenant_id: str, order_id: str, *, lock: bool = False
    ) -> PurchaseOrder:
        statement = select(PurchaseOrder).where(
            PurchaseOrder.tenant_id == tenant_id,
            or_(PurchaseOrder.id == order_id, PurchaseOrder.po_number == order_id),
        )
        if lock:
            statement = statement.with_for_update()
        value = await db.scalar(statement)
        if value is None:
            raise ERPNotFoundError("Purchase order was not found in this tenant.")
        return value

    @staticmethod
    async def _receipt(
        db: AsyncSession, tenant_id: str, receipt_id: str, *, lock: bool = False
    ) -> GoodsServiceReceipt:
        statement = select(GoodsServiceReceipt).where(
            GoodsServiceReceipt.tenant_id == tenant_id,
            or_(
                GoodsServiceReceipt.id == receipt_id,
                GoodsServiceReceipt.receipt_number == receipt_id,
            ),
        )
        if lock:
            statement = statement.with_for_update()
        value = await db.scalar(statement)
        if value is None:
            raise ERPNotFoundError("Receipt was not found in this tenant.")
        return value

    @staticmethod
    async def _invoice(
        db: AsyncSession, tenant_id: str, invoice_id: str
    ) -> SupplierInvoice:
        value = await db.scalar(
            select(SupplierInvoice).where(
                SupplierInvoice.tenant_id == tenant_id,
                or_(
                    SupplierInvoice.id == invoice_id,
                    SupplierInvoice.invoice_number == invoice_id,
                ),
            )
        )
        if value is None:
            raise ERPNotFoundError("Supplier invoice was not found in this tenant.")
        return value

    @staticmethod
    async def _match(
        db: AsyncSession, tenant_id: str, match_id: str, *, lock: bool = False
    ) -> InvoiceMatch:
        statement = select(InvoiceMatch).where(
            InvoiceMatch.tenant_id == tenant_id,
            InvoiceMatch.id == match_id,
        )
        if lock:
            statement = statement.with_for_update()
        value = await db.scalar(statement)
        if value is None:
            raise ERPNotFoundError("Invoice match was not found in this tenant.")
        return value

    def evidence_receipt(
        self, call_id: str, kind: str, tenant_id: str, refs: list[str]
    ) -> str:
        body = {"call_id": call_id, "kind": kind, "tenant_id": tenant_id, "refs": refs}
        signature = hmac.new(
            get_settings().mcp_token.get_secret_value().encode(),
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()[:24]
        return f"evr_erp_demo_{signature}"

    def _record(
        self,
        db: AsyncSession,
        aggregate: Any,
        event_type: str,
        actor: str,
        correlation_id: str,
        payload: dict[str, Any],
        *,
        actor_type: str = "USER",
    ) -> None:
        aggregate_type = type(aggregate).__name__.upper()
        version = int(getattr(aggregate, "version", 1))
        tenant_id = str(aggregate.tenant_id)
        db.add(
            AuditEvent(
                id=str(uuid4()),
                tenant_id=tenant_id,
                aggregate_type=aggregate_type,
                aggregate_id=str(aggregate.id),
                aggregate_version=version,
                event_type=event_type,
                actor_type=actor_type,
                actor_id=actor,
                payload=payload,
                correlation_id=correlation_id,
            )
        )
        db.add(
            OutboxEvent(
                id=str(uuid4()),
                tenant_id=tenant_id,
                aggregate_type=aggregate_type,
                aggregate_id=str(aggregate.id),
                aggregate_version=version,
                event_type=event_type,
                payload=payload,
                correlation_id=correlation_id,
            )
        )

    @staticmethod
    def _counterparty_projection(value: Counterparty) -> dict[str, Any]:
        return {
            "id": value.id,
            "business_id": value.business_id,
            "role": value.role,
            "legal_name": value.legal_name,
            "gstin": value.gstin,
            "relationship_status": value.relationship_status,
            "payment_terms_days": value.payment_terms_days,
            "approved_address": value.approved_address,
            "risk_flags": value.risk_flags,
            "version": value.version,
        }

    @staticmethod
    def _po_projection(value: PurchaseOrder) -> dict[str, Any]:
        return {
            "id": value.id,
            "po_number": value.po_number,
            "buyer_id": value.buyer_id,
            "supplier_business_id": value.supplier_business_id,
            "buyer_gstin": value.buyer_gstin,
            "seller_gstin": value.seller_gstin,
            "order_date": value.order_date.isoformat(),
            "expected_delivery_date": value.expected_delivery_date.isoformat()
            if value.expected_delivery_date
            else None,
            "currency": value.currency,
            "subtotal": str(value.subtotal),
            "tax": str(value.tax),
            "total": str(value.total),
            "payment_terms_days": value.payment_terms_days,
            "status": value.status,
            "approved_at": value.approved_at.isoformat() if value.approved_at else None,
            "approved_by": value.approved_by,
            "version": value.version,
        }

    @staticmethod
    def _po_line_projection(value: PurchaseOrderLine) -> dict[str, Any]:
        return {
            "id": value.id,
            "line_number": value.line_number,
            "sku": value.sku,
            "description": value.description,
            "quantity": str(value.quantity),
            "unit": value.unit,
            "unit_price": str(value.unit_price),
            "tax_rate": str(value.tax_rate),
            "line_total": str(value.line_total),
            "received_quantity": str(value.received_quantity),
            "accepted_quantity": str(value.accepted_quantity),
        }

    @staticmethod
    def _receipt_projection(value: GoodsServiceReceipt) -> dict[str, Any]:
        return {
            "id": value.id,
            "receipt_number": value.receipt_number,
            "purchase_order_id": value.purchase_order_id,
            "delivery_reference": value.delivery_reference,
            "receipt_type": value.receipt_type,
            "posting_date": value.posting_date.isoformat(),
            "receiver_token": value.receiver_token,
            "status": value.status,
            "accepted_value": str(value.accepted_value),
            "rejected_value": str(value.rejected_value),
            "source_hash": value.source_hash,
            "version": value.version,
        }

    @staticmethod
    def _receipt_line_projection(value: ReceiptLine) -> dict[str, Any]:
        return {
            "id": value.id,
            "purchase_order_line_id": value.purchase_order_line_id,
            "received_quantity": str(value.received_quantity),
            "accepted_quantity": str(value.accepted_quantity),
            "rejected_quantity": str(value.rejected_quantity),
            "accepted_value": str(value.accepted_value),
            "discrepancy": value.discrepancy,
        }

    def _match_projection(
        self,
        value: InvoiceMatch,
        invoice: SupplierInvoice,
        acceptance: InvoiceAcceptance | None,
    ) -> dict[str, Any]:
        return {
            "id": value.id,
            "invoice": {
                "id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "seller_gstin": invoice.seller_gstin,
                "buyer_gstin": invoice.buyer_gstin,
                "invoice_date": invoice.invoice_date.isoformat(),
                "claimed_total": str(invoice.claimed_total),
                "currency": invoice.currency,
                "gst_status": invoice.gst_status,
                "irn_token": invoice.irn_token,
                "source_version": invoice.source_version,
                "source_hash": invoice.source_hash,
            },
            "purchase_order_id": value.purchase_order_id,
            "receipt_id": value.receipt_id,
            "po_value": str(value.po_value),
            "receipt_value": str(value.receipt_value),
            "invoice_value": str(value.invoice_value),
            "supported_value": str(value.supported_value),
            "discrepancies": value.discrepancies,
            "status": value.status,
            "reviewed_by": value.reviewed_by,
            "version": value.version,
            "acceptance": self._acceptance_projection(acceptance) if acceptance else None,
        }

    @staticmethod
    def _acceptance_projection(value: InvoiceAcceptance) -> dict[str, Any]:
        return {
            "id": value.id,
            "accepted_amount": str(value.accepted_amount),
            "status": value.status,
            "reason": value.reason,
            "actor": value.actor,
            "accepted_at": value.accepted_at.isoformat(),
            "match_version": value.match_version,
        }

    @staticmethod
    def _audit_projection(value: AuditEvent) -> dict[str, Any]:
        return {
            "id": value.id,
            "aggregate_type": value.aggregate_type,
            "aggregate_id": value.aggregate_id,
            "aggregate_version": value.aggregate_version,
            "event_type": value.event_type,
            "actor_type": value.actor_type,
            "actor_id": value.actor_id,
            "payload": value.payload,
            "correlation_id": value.correlation_id,
            "occurred_at": value.occurred_at.isoformat(),
        }

    @staticmethod
    def _hash(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()


erp_service = ERPService()
