import json
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from pydantic import TypeAdapter
from sqlalchemy import select

from .database import session
from .models import BuyerAcceptance, Delivery, DeliveryEvent, DeliveryItem, ProofOfDelivery
from .schemas import FulfilmentClaim
from .security import verify_runtime_scope
from .service import DeliveryNotFoundError, delivery_service

mcp = MCPServer("xyena-synthetic-delivery-demo")


def _delivery_record(delivery: Delivery) -> dict[str, Any]:
    return {
        "id": delivery.id,
        "delivery_number": delivery.delivery_number,
        "purchase_order_id": delivery.purchase_order_id,
        "invoice_id": delivery.invoice_id,
        "invoice_number": delivery.invoice_number,
        "seller_business_id": delivery.seller_business_id,
        "buyer_id": delivery.buyer_id,
        "carrier_id": delivery.carrier_id,
        "tracking_number": delivery.tracking_number,
        "status": delivery.status,
        "declared_value": str(delivery.declared_value),
        "verified_delivered_value": str(delivery.verified_delivered_value),
        "exception_code": delivery.exception_code,
        "version": delivery.version,
    }


def _item_record(item: DeliveryItem) -> dict[str, Any]:
    return {
        "po_line_id": item.po_line_id,
        "invoice_line_id": item.invoice_line_id,
        "sku": item.sku,
        "unit": item.unit,
        "ordered_quantity": str(item.ordered_quantity),
        "dispatched_quantity": str(item.dispatched_quantity),
        "delivered_quantity": str(item.delivered_quantity),
        "accepted_quantity": str(item.accepted_quantity),
        "rejected_quantity": str(item.rejected_quantity),
        "supported_unit_value": str(item.supported_unit_value),
        "version": item.version,
    }


@mcp.tool(name="deliveries.get")
async def deliveries_get(delivery_id: str, ctx: Context) -> dict[str, Any]:
    """Get a tenant-scoped delivery and its source delivery lines."""
    scope = verify_runtime_scope(ctx, "delivery.deliveries.get")
    try:
        result = await delivery_service.get_delivery(scope.tenant_id, delivery_id)
    except DeliveryNotFoundError:
        return {"status": "NOT_FOUND", "message": "Delivery not found."}
    delivery = result["delivery"]
    return delivery_service.source_envelope(
        "xyena-demo-delivery", scope.call_id, delivery.version,
        {"status": "SUCCESS", "delivery": _delivery_record(delivery), "items": [_item_record(i) for i in result["items"]]},
        delivery.updated_at,
    )


@mcp.tool(name="deliveries.find_by_invoice")
async def deliveries_find_by_invoice(
    invoice_id: str | None = None,
    seller_id: str | None = None,
    invoice_number: str | None = None,
    ctx: Context = None,
) -> dict[str, Any]:
    """Find tenant-scoped deliveries by invoice identity."""
    scope = verify_runtime_scope(ctx, "delivery.deliveries.find_by_invoice")
    if not invoice_id and not (seller_id and invoice_number):
        return delivery_service.source_envelope("xyena-demo-delivery", scope.call_id, 0, {"status": "INVALID_REQUEST", "message": "Use invoice_id, or seller_id with invoice_number."})
    async with session() as db:
        query = select(Delivery).where(Delivery.tenant_id == scope.tenant_id)
        if invoice_id:
            query = query.where(Delivery.invoice_id == invoice_id)
        else:
            query = query.where(Delivery.seller_business_id == seller_id, Delivery.invoice_number == invoice_number)
        results = (await db.scalars(query)).all()
    version = max((d.version for d in results), default=0)
    return delivery_service.source_envelope("xyena-demo-delivery", scope.call_id, version, {"status": "SUCCESS", "deliveries": [_delivery_record(d) for d in results]})


@mcp.tool(name="deliveries.find_by_po")
async def deliveries_find_by_po(purchase_order_id: str, ctx: Context) -> dict[str, Any]:
    """Find tenant-scoped deliveries by purchase-order identity."""
    scope = verify_runtime_scope(ctx, "delivery.deliveries.find_by_po")
    async with session() as db:
        results = (await db.scalars(select(Delivery).where(
            Delivery.tenant_id == scope.tenant_id,
            Delivery.purchase_order_id == purchase_order_id,
        ))).all()
    version = max((d.version for d in results), default=0)
    return delivery_service.source_envelope("xyena-demo-delivery", scope.call_id, version, {"status": "SUCCESS", "deliveries": [_delivery_record(d) for d in results]})


@mcp.tool(name="events.list")
async def events_list(delivery_id: str, ctx: Context) -> dict[str, Any]:
    """Return the immutable source event timeline for a tenant-scoped delivery."""
    scope = verify_runtime_scope(ctx, "delivery.events.list")
    async with session() as db:
        delivery = await db.scalar(select(Delivery).where(Delivery.id == delivery_id, Delivery.tenant_id == scope.tenant_id))
        if delivery is None:
            return {"status": "NOT_FOUND", "message": "Delivery not found."}
        events = (await db.scalars(select(DeliveryEvent).where(DeliveryEvent.delivery_id == delivery.id).order_by(DeliveryEvent.occurred_at))).all()
    data = [{"id": e.id, "event_type": e.event_type, "occurred_at": e.occurred_at.isoformat(), "actor": e.actor, "location": json.loads(e.location) if e.location else None, "notes": e.notes, "prior_status": e.prior_status, "new_status": e.new_status, "version": e.version} for e in events]
    return delivery_service.source_envelope("xyena-demo-delivery", scope.call_id, delivery.version, {"status": "SUCCESS", "delivery_id": delivery.id, "events": data}, delivery.updated_at)


@mcp.tool(name="proofs.get")
async def proofs_get(delivery_id: str, ctx: Context) -> dict[str, Any]:
    """Return safe POD metadata and verification state; object keys and recipient identity stay restricted."""
    scope = verify_runtime_scope(ctx, "delivery.proofs.get")
    async with session() as db:
        delivery = await db.scalar(select(Delivery).where(Delivery.id == delivery_id, Delivery.tenant_id == scope.tenant_id))
        if delivery is None:
            return {"status": "NOT_FOUND", "message": "Delivery not found."}
        proofs = (await db.scalars(select(ProofOfDelivery).where(ProofOfDelivery.delivery_id == delivery.id).order_by(ProofOfDelivery.captured_at.desc()))).all()
    data = [{"id": p.id, "proof_type": p.proof_type, "content_hash": p.content_hash, "mime_type": p.mime_type, "captured_at": p.captured_at.isoformat(), "verification_status": p.verification_status, "verification_method": p.verification_method, "security_flags": json.loads(p.security_flags or "[]")} for p in proofs]
    return delivery_service.source_envelope("xyena-demo-delivery", scope.call_id, delivery.version, {"status": "SUCCESS", "delivery_id": delivery.id, "proofs": data}, delivery.updated_at)


@mcp.tool(name="acceptance.get")
async def acceptance_get(delivery_id: str, ctx: Context) -> dict[str, Any]:
    """Return the latest buyer acceptance source record and its line snapshot."""
    scope = verify_runtime_scope(ctx, "delivery.acceptance.get")
    async with session() as db:
        delivery = await db.scalar(select(Delivery).where(Delivery.id == delivery_id, Delivery.tenant_id == scope.tenant_id))
        if delivery is None:
            return {"status": "NOT_FOUND", "message": "Delivery not found."}
        acceptance = await db.scalar(select(BuyerAcceptance).where(BuyerAcceptance.delivery_id == delivery.id).order_by(BuyerAcceptance.occurred_at.desc()).limit(1))
    data: dict[str, Any] = {"status": "PENDING", "delivery_id": delivery.id}
    if acceptance:
        data = {"status": "SUCCESS", "delivery_id": delivery.id, "acceptance": {"id": acceptance.id, "buyer_identity": acceptance.buyer_identity, "status": acceptance.status, "accepted_value": str(acceptance.accepted_value), "occurred_at": acceptance.occurred_at.isoformat(), "reason": acceptance.reason, "items": json.loads(acceptance.item_level_acceptance), "source_hash": acceptance.source_hash}}
    return delivery_service.source_envelope("xyena-demo-delivery", scope.call_id, delivery.version, data, delivery.updated_at)


@mcp.tool(name="fulfilment.verify")
async def fulfilment_verify(claims: list[dict[str, Any]], ctx: Context) -> dict[str, Any]:
    """Verify explicit invoice/PO line claims against independently accepted delivery quantities."""
    scope = verify_runtime_scope(ctx, "delivery.fulfilment.verify")
    validated = TypeAdapter(list[FulfilmentClaim]).validate_python(claims)
    result = await delivery_service.verify_fulfilment(scope.tenant_id, validated)
    version = result.pop("record_version")
    return delivery_service.source_envelope("xyena-demo-delivery", scope.call_id, version, {"status": "SUCCESS", **result})


mcp_app = mcp.streamable_http_app(streamable_http_path="/", stateless_http=True, json_response=True)
