import hashlib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from .database import session
from .models import (
    AuditEvent,
    Counterparty,
    GoodsServiceReceipt,
    InvoiceAcceptance,
    InvoiceMatch,
    OutboxEvent,
    PurchaseOrder,
    PurchaseOrderLine,
    ReceiptLine,
    SupplierInvoice,
)

DEMO_TENANT_ID = "00000000-0000-4000-8000-000000000101"
DEMO_ORGANIZATION_ID = "00000000-0000-4000-8000-000000000301"
DEMO_USER_ID = "00000000-0000-4000-8000-000000000201"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def seed_demo_data() -> None:
    async with session() as db:
        if await db.get(PurchaseOrder, "po_demo_1007") is not None:
            return

        db.add_all(
            [
                Counterparty(
                    id="cp_demo_buyer",
                    tenant_id=DEMO_TENANT_ID,
                    business_id="buyer_demo_industries",
                    role="BUYER",
                    legal_name="Northstar Industrial Systems Limited",
                    gstin="29AABCB1234F1Z5",
                    relationship_status="APPROVED",
                    payment_terms_days=45,
                    approved_address="Peenya Industrial Area, Bengaluru, Karnataka",
                    risk_flags=[],
                ),
                Counterparty(
                    id="cp_demo_supplier_primary",
                    tenant_id=DEMO_TENANT_ID,
                    business_id="supplier_demo_components",
                    role="SUPPLIER",
                    legal_name="Meridian Components Private Limited",
                    gstin="29AABCS5678K1Z2",
                    relationship_status="APPROVED",
                    payment_terms_days=45,
                    approved_address="Bommasandra Industrial Area, Bengaluru, Karnataka",
                    risk_flags=[],
                ),
                Counterparty(
                    id="cp_demo_supplier_review",
                    tenant_id=DEMO_TENANT_ID,
                    business_id="supplier_demo_services",
                    role="SUPPLIER",
                    legal_name="Civic Field Services LLP",
                    gstin="29AACFC9087M1Z4",
                    relationship_status="REVIEW_REQUIRED",
                    payment_terms_days=30,
                    approved_address="Yeshwanthpur, Bengaluru, Karnataka",
                    risk_flags=["BANK_DETAILS_PENDING_REVIEW"],
                ),
            ]
        )

        po1 = PurchaseOrder(
            id="po_demo_1007",
            tenant_id=DEMO_TENANT_ID,
            po_number="PO-1007",
            buyer_id="buyer_demo_industries",
            supplier_business_id="supplier_demo_components",
            buyer_gstin="29AABCB1234F1Z5",
            seller_gstin="29AABCS5678K1Z2",
            order_date=date.today() - timedelta(days=38),
            expected_delivery_date=date.today() - timedelta(days=18),
            currency="INR",
            subtotal=Decimal("500000.00"),
            tax=Decimal("90000.00"),
            total=Decimal("590000.00"),
            payment_terms_days=45,
            status="FULFILLED",
            approved_at=datetime.now(UTC) - timedelta(days=36),
            approved_by="procurement_demo_reviewer",
            version=4,
        )
        po2 = PurchaseOrder(
            id="po_demo_1012",
            tenant_id=DEMO_TENANT_ID,
            po_number="PO-1012",
            buyer_id="buyer_demo_industries",
            supplier_business_id="supplier_demo_components",
            buyer_gstin="29AABCB1234F1Z5",
            seller_gstin="29AABCS5678K1Z2",
            order_date=date.today() - timedelta(days=16),
            expected_delivery_date=date.today() + timedelta(days=4),
            currency="INR",
            subtotal=Decimal("300000.00"),
            tax=Decimal("54000.00"),
            total=Decimal("354000.00"),
            payment_terms_days=45,
            status="PARTIALLY_FULFILLED",
            approved_at=datetime.now(UTC) - timedelta(days=14),
            approved_by="procurement_demo_reviewer",
            version=3,
        )
        po3 = PurchaseOrder(
            id="po_demo_1018",
            tenant_id=DEMO_TENANT_ID,
            po_number="PO-1018",
            buyer_id="buyer_demo_industries",
            supplier_business_id="supplier_demo_services",
            buyer_gstin="29AABCB1234F1Z5",
            seller_gstin="29AACFC9087M1Z4",
            order_date=date.today() - timedelta(days=2),
            expected_delivery_date=date.today() + timedelta(days=20),
            currency="INR",
            subtotal=Decimal("120000.00"),
            tax=Decimal("21600.00"),
            total=Decimal("141600.00"),
            payment_terms_days=30,
            status="SUBMITTED",
            version=2,
        )
        db.add_all([po1, po2, po3])
        await db.flush()

        lines = [
            PurchaseOrderLine(
                id="pol_demo_1007_1",
                purchase_order_id=po1.id,
                line_number=1,
                sku="MOTOR-4KW",
                description="Industrial motor assembly, 4 kW",
                quantity=Decimal("10"),
                unit="EA",
                unit_price=Decimal("30000.00"),
                tax_rate=Decimal("18.00"),
                line_total=Decimal("300000.00"),
                received_quantity=Decimal("10"),
                accepted_quantity=Decimal("10"),
            ),
            PurchaseOrderLine(
                id="pol_demo_1007_2",
                purchase_order_id=po1.id,
                line_number=2,
                sku="CTRL-PANEL",
                description="Control panel enclosure and wiring",
                quantity=Decimal("5"),
                unit="EA",
                unit_price=Decimal("40000.00"),
                tax_rate=Decimal("18.00"),
                line_total=Decimal("200000.00"),
                received_quantity=Decimal("5"),
                accepted_quantity=Decimal("5"),
            ),
            PurchaseOrderLine(
                id="pol_demo_1012_1",
                purchase_order_id=po2.id,
                line_number=1,
                sku="GEARBOX-A2",
                description="Precision gearbox assembly",
                quantity=Decimal("20"),
                unit="EA",
                unit_price=Decimal("15000.00"),
                tax_rate=Decimal("18.00"),
                line_total=Decimal("300000.00"),
                received_quantity=Decimal("10"),
                accepted_quantity=Decimal("10"),
            ),
            PurchaseOrderLine(
                id="pol_demo_1018_1",
                purchase_order_id=po3.id,
                line_number=1,
                sku="FIELD-CAL",
                description="Quarterly field calibration service",
                quantity=Decimal("1"),
                unit="JOB",
                unit_price=Decimal("120000.00"),
                tax_rate=Decimal("18.00"),
                line_total=Decimal("120000.00"),
                received_quantity=Decimal("0"),
                accepted_quantity=Decimal("0"),
            ),
        ]
        db.add_all(lines)
        await db.flush()

        receipt1 = GoodsServiceReceipt(
            id="rcpt_demo_501",
            tenant_id=DEMO_TENANT_ID,
            receipt_number="GRN-501",
            purchase_order_id=po1.id,
            delivery_reference="DEL-7781",
            receipt_type="GOODS",
            posting_date=date.today() - timedelta(days=17),
            receiver_token="warehouse_user_demo_01",
            status="POSTED",
            accepted_value=Decimal("590000.00"),
            rejected_value=Decimal("0.00"),
            source_hash=_hash("GRN-501|PO-1007|590000.00"),
            version=2,
        )
        receipt2 = GoodsServiceReceipt(
            id="rcpt_demo_506",
            tenant_id=DEMO_TENANT_ID,
            receipt_number="GRN-506",
            purchase_order_id=po2.id,
            delivery_reference="DEL-7814",
            receipt_type="GOODS",
            posting_date=date.today() - timedelta(days=3),
            receiver_token="warehouse_user_demo_02",
            status="POSTED",
            accepted_value=Decimal("177000.00"),
            rejected_value=Decimal("0.00"),
            source_hash=_hash("GRN-506|PO-1012|177000.00"),
            version=2,
        )
        db.add_all([receipt1, receipt2])
        await db.flush()
        db.add_all(
            [
                ReceiptLine(
                    id="rcl_demo_501_1",
                    receipt_id=receipt1.id,
                    purchase_order_line_id="pol_demo_1007_1",
                    received_quantity=Decimal("10"),
                    accepted_quantity=Decimal("10"),
                    rejected_quantity=Decimal("0"),
                    accepted_value=Decimal("354000.00"),
                ),
                ReceiptLine(
                    id="rcl_demo_501_2",
                    receipt_id=receipt1.id,
                    purchase_order_line_id="pol_demo_1007_2",
                    received_quantity=Decimal("5"),
                    accepted_quantity=Decimal("5"),
                    rejected_quantity=Decimal("0"),
                    accepted_value=Decimal("236000.00"),
                ),
                ReceiptLine(
                    id="rcl_demo_506_1",
                    receipt_id=receipt2.id,
                    purchase_order_line_id="pol_demo_1012_1",
                    received_quantity=Decimal("10"),
                    accepted_quantity=Decimal("10"),
                    rejected_quantity=Decimal("0"),
                    accepted_value=Decimal("177000.00"),
                    discrepancy="Remaining 10 units not yet delivered",
                ),
            ]
        )

        invoices = [
            SupplierInvoice(
                id="inv_demo_2041",
                tenant_id=DEMO_TENANT_ID,
                invoice_number="INV-2041",
                seller_gstin="29AABCS5678K1Z2",
                buyer_gstin="29AABCB1234F1Z5",
                purchase_order_id=po1.id,
                invoice_date=date.today() - timedelta(days=15),
                currency="INR",
                claimed_total=Decimal("590000.00"),
                gst_status="REGISTERED",
                irn_token="irn_demo_a19f41",
                source_version=4,
                source_hash=_hash("INV-2041|590000.00|REGISTERED|4"),
                matching_status="ACCEPTED",
            ),
            SupplierInvoice(
                id="inv_demo_2048",
                tenant_id=DEMO_TENANT_ID,
                invoice_number="INV-2048",
                seller_gstin="29AABCS5678K1Z2",
                buyer_gstin="29AABCB1234F1Z5",
                purchase_order_id=po2.id,
                invoice_date=date.today() - timedelta(days=2),
                currency="INR",
                claimed_total=Decimal("354000.00"),
                gst_status="REGISTERED",
                irn_token="irn_demo_d0e284",
                source_version=2,
                source_hash=_hash("INV-2048|354000.00|REGISTERED|2"),
                matching_status="PARTIAL_MATCH",
            ),
            SupplierInvoice(
                id="inv_demo_2099",
                tenant_id=DEMO_TENANT_ID,
                invoice_number="INV-2099",
                seller_gstin="29AACFC9087M1Z4",
                buyer_gstin="29AABCB1234F1Z5",
                purchase_order_id=None,
                invoice_date=date.today() - timedelta(days=1),
                currency="INR",
                claimed_total=Decimal("210000.00"),
                gst_status="REGISTERED",
                irn_token="irn_demo_68b73c",
                source_version=1,
                source_hash=_hash("INV-2099|210000.00|REGISTERED|1"),
                matching_status="MISMATCHED",
            ),
        ]
        db.add_all(invoices)
        await db.flush()
        matches = [
            InvoiceMatch(
                id="match_demo_2041",
                tenant_id=DEMO_TENANT_ID,
                invoice_id="inv_demo_2041",
                purchase_order_id=po1.id,
                receipt_id=receipt1.id,
                po_value=Decimal("590000.00"),
                receipt_value=Decimal("590000.00"),
                invoice_value=Decimal("590000.00"),
                supported_value=Decimal("590000.00"),
                tolerance_amount=Decimal("1.00"),
                discrepancies=[],
                status="ACCEPTED",
                reviewed_by="ap_demo_reviewer",
                version=3,
            ),
            InvoiceMatch(
                id="match_demo_2048",
                tenant_id=DEMO_TENANT_ID,
                invoice_id="inv_demo_2048",
                purchase_order_id=po2.id,
                receipt_id=receipt2.id,
                po_value=Decimal("354000.00"),
                receipt_value=Decimal("177000.00"),
                invoice_value=Decimal("354000.00"),
                supported_value=Decimal("177000.00"),
                tolerance_amount=Decimal("1.00"),
                discrepancies=["PARTIAL_RECEIPT"],
                status="PARTIAL_MATCH",
                version=2,
            ),
            InvoiceMatch(
                id="match_demo_2099",
                tenant_id=DEMO_TENANT_ID,
                invoice_id="inv_demo_2099",
                purchase_order_id=None,
                receipt_id=None,
                po_value=Decimal("0.00"),
                receipt_value=Decimal("0.00"),
                invoice_value=Decimal("210000.00"),
                supported_value=Decimal("0.00"),
                tolerance_amount=Decimal("1.00"),
                discrepancies=["PURCHASE_ORDER_NOT_FOUND", "SUPPLIER_RELATIONSHIP_REVIEW_REQUIRED"],
                status="MISMATCHED",
                version=1,
            ),
        ]
        db.add_all(matches)
        await db.flush()
        db.add(
            InvoiceAcceptance(
                id="accept_demo_2041",
                tenant_id=DEMO_TENANT_ID,
                match_id="match_demo_2041",
                accepted_amount=Decimal("590000.00"),
                status="ACCEPTED",
                reason="PO, posted receipt, GST invoice and values match",
                actor="ap_demo_reviewer",
                accepted_at=datetime.now(UTC) - timedelta(days=12),
                match_version=3,
            )
        )
        db.add_all(
            [
                AuditEvent(
                    id="audit_demo_po_1007",
                    tenant_id=DEMO_TENANT_ID,
                    aggregate_type="PurchaseOrder",
                    aggregate_id=po1.id,
                    aggregate_version=2,
                    event_type="purchase_order.approved",
                    actor_type="USER",
                    actor_id="procurement_demo_reviewer",
                    reason="Approved supplier and budget",
                    payload={"po_number": po1.po_number, "total": str(po1.total)},
                    correlation_id="corr_demo_po_1007",
                    occurred_at=datetime.now(UTC) - timedelta(days=36),
                ),
                AuditEvent(
                    id="audit_demo_receipt_501",
                    tenant_id=DEMO_TENANT_ID,
                    aggregate_type="GoodsServiceReceipt",
                    aggregate_id=receipt1.id,
                    aggregate_version=2,
                    event_type="receipt.posted",
                    actor_type="USER",
                    actor_id="warehouse_user_demo_01",
                    reason="Warehouse receipt posted",
                    payload={"receipt_number": receipt1.receipt_number},
                    correlation_id="corr_demo_receipt_501",
                    occurred_at=datetime.now(UTC) - timedelta(days=17),
                ),
                AuditEvent(
                    id="audit_demo_match_2041",
                    tenant_id=DEMO_TENANT_ID,
                    aggregate_type="InvoiceMatch",
                    aggregate_id="match_demo_2041",
                    aggregate_version=3,
                    event_type="invoice_match.accepted",
                    actor_type="USER",
                    actor_id="ap_demo_reviewer",
                    reason="Three-way match accepted",
                    payload={"accepted_amount": "590000.00"},
                    correlation_id="corr_demo_match_2041",
                    occurred_at=datetime.now(UTC) - timedelta(days=12),
                ),
                AuditEvent(
                    id="audit_demo_match_2048",
                    tenant_id=DEMO_TENANT_ID,
                    aggregate_type="InvoiceMatch",
                    aggregate_id="match_demo_2048",
                    aggregate_version=2,
                    event_type="invoice_match.review_required",
                    actor_type="SERVICE",
                    actor_id="buyer_erp_matcher",
                    reason="Remaining goods have not been received",
                    payload={"discrepancy": "PARTIAL_RECEIPT"},
                    correlation_id="corr_demo_match_2048",
                    occurred_at=datetime.now(UTC) - timedelta(days=2),
                ),
            ]
        )
        db.add_all(
            [
                OutboxEvent(
                    id="outbox_demo_match_2041",
                    tenant_id=DEMO_TENANT_ID,
                    aggregate_type="InvoiceMatch",
                    aggregate_id="match_demo_2041",
                    aggregate_version=3,
                    event_type="invoice_match.accepted",
                    payload={"accepted_amount": "590000.00"},
                    correlation_id="corr_demo_match_2041",
                    created_at=datetime.now(UTC) - timedelta(days=12),
                    published_at=datetime.now(UTC) - timedelta(days=12),
                    attempt_count=1,
                ),
                OutboxEvent(
                    id="outbox_demo_match_2048",
                    tenant_id=DEMO_TENANT_ID,
                    aggregate_type="InvoiceMatch",
                    aggregate_id="match_demo_2048",
                    aggregate_version=2,
                    event_type="invoice_match.review_required",
                    payload={"discrepancy": "PARTIAL_RECEIPT"},
                    correlation_id="corr_demo_match_2048",
                    created_at=datetime.now(UTC) - timedelta(days=2),
                    published_at=None,
                    attempt_count=0,
                ),
            ]
        )
