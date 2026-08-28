from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from sqlalchemy import select

from .database import session
from .models import (
    BuyerAcceptance,
    Delivery,
    DeliveryEvent,
    DeliveryItem,
    ProofOfDelivery,
)
from .security import verify_runtime_scope
from .service import delivery_service


mcp = MCPServer("xyena-synthetic-delivery-demo")


@mcp.tool(name="deliveries.get")
async def deliveries_get(delivery_id: str, ctx: Context) -> dict[str, Any]:
    """Get the current delivery record, line items, version and status by delivery ID."""
    scope = verify_runtime_scope(ctx, "delivery.deliveries.get")
    async with session() as db:
        res = await db.scalar(
            select(Delivery).where(
                Delivery.id == delivery_id,
                Delivery.tenant_id == scope.tenant_id,
            )
        )
        if not res:
            return {"status": "NOT_FOUND", "message": "Delivery not found."}

        items = (
            await db.scalars(
                select(DeliveryItem).where(DeliveryItem.delivery_id == delivery_id)
            )
        ).all()

        return {
            "status": "SUCCESS",
            "delivery": {
                "id": res.id,
                "delivery_number": res.delivery_number,
                "purchase_order_id": res.purchase_order_id,
                "invoice_id": res.invoice_id,
                "invoice_number": res.invoice_number,
                "status": res.status,
                "declared_value": str(res.declared_value),
                "verified_delivered_value": str(res.verified_delivered_value),
                "version": res.version,
                "exception_code": res.exception_code,
                "dispatch_date": res.dispatch_date.isoformat() if res.dispatch_date else None,
                "delivered_at": res.delivered_at.isoformat() if res.delivered_at else None,
            },
            "items": [
                {
                    "sku": item.sku,
                    "description": item.description,
                    "unit": item.unit,
                    "ordered_quantity": str(item.ordered_quantity),
                    "dispatched_quantity": str(item.dispatched_quantity),
                    "delivered_quantity": str(item.delivered_quantity),
                    "accepted_quantity": str(item.accepted_quantity),
                    "rejected_quantity": str(item.rejected_quantity),
                    "supported_unit_value": str(item.supported_unit_value),
                }
                for item in items
            ],
            "evidence_receipt_id": delivery_service._receipt(scope, "deliveries.get", [res.id, res.status]),
            "security_flags": ["SYNTHETIC_DATA"],
        }


@mcp.tool(name="deliveries.find_by_invoice")
async def deliveries_find_by_invoice(
    invoice_id: str | None = None,
    seller_id: str | None = None,
    invoice_number: str | None = None,
    ctx: Context = None,
) -> dict[str, Any]:
    """Find delivery records matching an invoice ID, or seller ID and invoice number."""
    scope = verify_runtime_scope(ctx, "delivery.deliveries.find_by_invoice")
    async with session() as db:
        query = select(Delivery).where(Delivery.tenant_id == scope.tenant_id)
        if invoice_id:
            query = query.where(Delivery.invoice_id == invoice_id)
        if seller_id:
            query = query.where(Delivery.seller_business_id == seller_id)
        if invoice_number:
            query = query.where(Delivery.invoice_number == invoice_number)

        results = (await db.scalars(query)).all()

        return {
            "status": "SUCCESS",
            "deliveries": [
                {
                    "id": d.id,
                    "delivery_number": d.delivery_number,
                    "purchase_order_id": d.purchase_order_id,
                    "invoice_id": d.invoice_id,
                    "invoice_number": d.invoice_number,
                    "status": d.status,
                    "declared_value": str(d.declared_value),
                    "verified_delivered_value": str(d.verified_delivered_value),
                    "version": d.version,
                }
                for d in results
            ],
            "evidence_receipt_id": delivery_service._receipt(scope, "deliveries.find_by_invoice", [d.id for d in results]),
            "security_flags": ["SYNTHETIC_DATA"],
        }


@mcp.tool(name="deliveries.find_by_po")
async def deliveries_find_by_po(purchase_order_id: str, ctx: Context) -> dict[str, Any]:
    """Find delivery records associated with a specific purchase order ID."""
    scope = verify_runtime_scope(ctx, "delivery.deliveries.find_by_po")
    async with session() as db:
        results = (
            await db.scalars(
                select(Delivery).where(
                    Delivery.purchase_order_id == purchase_order_id,
                    Delivery.tenant_id == scope.tenant_id,
                )
            )
        ).all()

        return {
            "status": "SUCCESS",
            "deliveries": [
                {
                    "id": d.id,
                    "delivery_number": d.delivery_number,
                    "purchase_order_id": d.purchase_order_id,
                    "invoice_id": d.invoice_id,
                    "status": d.status,
                    "declared_value": str(d.declared_value),
                    "verified_delivered_value": str(d.verified_delivered_value),
                    "version": d.version,
                }
                for d in results
            ],
            "evidence_receipt_id": delivery_service._receipt(scope, "deliveries.find_by_po", [d.id for d in results]),
            "security_flags": ["SYNTHETIC_DATA"],
        }


@mcp.tool(name="events.list")
async def events_list(delivery_id: str, ctx: Context) -> dict[str, Any]:
    """Retrieve the ordered, immutable timeline of events for a delivery."""
    scope = verify_runtime_scope(ctx, "delivery.events.list")
    async with session() as db:
        # Verify tenant scope
        deliv = await db.scalar(
            select(Delivery).where(
                Delivery.id == delivery_id,
                Delivery.tenant_id == scope.tenant_id,
            )
        )
        if not deliv:
            return {"status": "NOT_FOUND", "message": "Delivery not found."}

        events = (
            await db.scalars(
                select(DeliveryEvent)
                .where(DeliveryEvent.delivery_id == delivery_id)
                .order_by(DeliveryEvent.occurred_at.asc())
            )
        ).all()

        return {
            "status": "SUCCESS",
            "delivery_id": delivery_id,
            "events": [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "occurred_at": e.occurred_at.isoformat(),
                    "actor": e.actor,
                    "location": e.location,
                    "notes": e.notes,
                    "prior_status": e.prior_status,
                    "new_status": e.new_status,
                    "version": e.version,
                }
                for e in events
            ],
            "evidence_receipt_id": delivery_service._receipt(scope, "events.list", [e.id for e in events]),
            "security_flags": ["SYNTHETIC_DATA"],
        }


@mcp.tool(name="proofs.get")
async def proofs_get(delivery_id: str, ctx: Context) -> dict[str, Any]:
    """Retrieve Proof of Delivery (POD) metadata, hashes, and verification status for a delivery."""
    scope = verify_runtime_scope(ctx, "delivery.proofs.get")
    async with session() as db:
        deliv = await db.scalar(
            select(Delivery).where(
                Delivery.id == delivery_id,
                Delivery.tenant_id == scope.tenant_id,
            )
        )
        if not deliv:
            return {"status": "NOT_FOUND", "message": "Delivery not found."}

        pods = (
            await db.scalars(
                select(ProofOfDelivery)
                .where(ProofOfDelivery.delivery_id == delivery_id)
                .order_by(ProofOfDelivery.captured_at.desc())
            )
        ).all()

        return {
            "status": "SUCCESS",
            "delivery_id": delivery_id,
            "proofs": [
                {
                    "id": p.id,
                    "proof_type": p.proof_type,
                    "restricted_object_key": p.restricted_object_key,
                    "content_hash": p.content_hash,
                    "mime_type": p.mime_type,
                    "captured_at": p.captured_at.isoformat(),
                    "recipient_name": p.recipient_name,
                    "recipient_role": p.recipient_role,
                    "verification_status": p.verification_status,
                    "verifier": p.verifier,
                }
                for p in pods
            ],
            "evidence_receipt_id": delivery_service._receipt(scope, "proofs.get", [p.id for p in pods]),
            "security_flags": ["SYNTHETIC_DATA"],
        }


@mcp.tool(name="acceptance.get")
async def acceptance_get(delivery_id: str, ctx: Context) -> dict[str, Any]:
    """Retrieve the latest buyer acceptance details and item quantity snapshot."""
    scope = verify_runtime_scope(ctx, "delivery.acceptance.get")
    async with session() as db:
        deliv = await db.scalar(
            select(Delivery).where(
                Delivery.id == delivery_id,
                Delivery.tenant_id == scope.tenant_id,
            )
        )
        if not deliv:
            return {"status": "NOT_FOUND", "message": "Delivery not found."}

        acceptance = await db.scalar(
            select(BuyerAcceptance)
            .where(BuyerAcceptance.delivery_id == delivery_id)
            .order_by(BuyerAcceptance.occurred_at.desc())
            .limit(1)
        )

        if not acceptance:
            return {
                "status": "PENDING",
                "message": "No buyer acceptance has been recorded yet.",
            }

        return {
            "status": "SUCCESS",
            "delivery_id": delivery_id,
            "acceptance": {
                "id": acceptance.id,
                "buyer_identity": acceptance.buyer_identity,
                "status": acceptance.status,
                "accepted_value": str(acceptance.accepted_value),
                "occurred_at": acceptance.occurred_at.isoformat(),
                "actor": acceptance.actor,
                "reason": acceptance.reason,
                "item_level_acceptance": json.loads(acceptance.item_level_acceptance),
            },
            "evidence_receipt_id": delivery_service._receipt(scope, "acceptance.get", [acceptance.id]),
            "security_flags": ["SYNTHETIC_DATA"],
        }


@mcp.tool(name="fulfilment.verify")
async def fulfilment_verify(claims: list[dict[str, Any]], ctx: Context) -> dict[str, Any]:
    """Verify purchase-order/invoice line claims against accepted quantities in delivery database."""
    scope = verify_runtime_scope(ctx, "delivery.fulfilment.verify")
    async with session() as db:
        matches = []
        unmatched = []
        contradictions = []
        fresh_until = datetime.now(UTC) + timedelta(minutes=15)

        for claim in claims:
            po_line_id = claim.get("po_line_id")
            invoice_line_id = claim.get("invoice_line_id")
            sku = claim.get("sku")
            claimed_qty = Decimal(str(claim.get("claimed_quantity", 0)))
            claimed_val = Decimal(str(claim.get("claimed_unit_value", 0)))

            # Query matching non-cancelled items
            query = select(DeliveryItem).join(Delivery, Delivery.id == DeliveryItem.delivery_id).where(
                Delivery.tenant_id == scope.tenant_id,
                Delivery.status != "CANCELLED",
            )
            if po_line_id:
                query = query.where(DeliveryItem.po_line_id == po_line_id)
            elif invoice_line_id:
                query = query.where(DeliveryItem.invoice_line_id == invoice_line_id)
            elif sku:
                query = query.where(DeliveryItem.sku == sku)
            else:
                unmatched.append({**claim, "reason": "No line identification provided (po_line_id, invoice_line_id or sku)"})
                continue

            items = (await db.scalars(query)).all()
            if not items:
                unmatched.append({**claim, "reason": "No matching delivery records found"})
                continue

            # Sum up accepted quantities across matching deliveries
            accepted_qty = sum(item.accepted_quantity for item in items)
            supported_unit_val = items[0].supported_unit_value  # Assume consistent unit value

            line_match = True
            errors = []

            if accepted_qty != claimed_qty:
                line_match = False
                errors.append({
                    "code": "QUANTITY_MISMATCH",
                    "message": f"Claimed quantity {claimed_qty} does not match verified accepted quantity {accepted_qty}",
                })
            if supported_unit_val != claimed_val:
                line_match = False
                errors.append({
                    "code": "VALUE_MISMATCH",
                    "message": f"Claimed unit value {claimed_val} does not match supported unit value {supported_unit_val}",
                })

            result_entry = {
                "po_line_id": po_line_id,
                "invoice_line_id": invoice_line_id,
                "sku": sku,
                "claimed_quantity": str(claimed_qty),
                "accepted_quantity": str(accepted_qty),
                "claimed_unit_value": str(claimed_val),
                "supported_unit_value": str(supported_unit_val),
            }

            if line_match:
                matches.append(result_entry)
            else:
                contradictions.append({**result_entry, "errors": errors})

        refs = [c.get("po_line_id") or c.get("sku") or "unknown" for c in claims]
        return {
            "status": "SUCCESS",
            "matches": matches,
            "unmatched_lines": unmatched,
            "contradiction_lines": contradictions,
            "freshness": {
                "retrieved_at": datetime.now(UTC).isoformat(),
                "fresh_until": fresh_until.isoformat(),
            },
            "evidence_receipt_id": delivery_service._receipt(scope, "fulfilment.verify", refs),
            "security_flags": ["SYNTHETIC_DATA"],
        }


mcp_app = mcp.streamable_http_app(
    streamable_http_path="/", stateless_http=True, json_response=True
)
