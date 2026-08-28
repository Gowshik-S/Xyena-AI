from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid5

from .auth import hash_password
from .database import session
from .domain import THRESHOLD_VERSION, calculate_line, canonical_hash, financial_year, money
from .models import (
    AuditEvent,
    ClassificationSnapshot,
    Enterprise,
    EnterpriseMembership,
    Invoice,
    InvoiceLine,
    InvoiceStatusHistory,
    ReturnSummary,
    Taxpayer,
    User,
)
from .settings import get_settings


NAMESPACE = UUID("00000000-0000-4000-8000-000000009901")

ENTERPRISE_FIXTURES = [
    {
        "slug": "micro",
        "tenant_id": "00000000-0000-4000-8000-000000001101",
        "enterprise_id": "00000000-0000-4000-8000-000000001201",
        "business_id": "biz_gst_micro_01",
        "legal_name": "Kaveri Precision Components Private Limited",
        "trade_name": "Kaveri Precision",
        "gstin": "29ABCDE1234F1Z5",
        "state_code": "29",
        "classification": "MICRO",
        "investment": Decimal("12000000.00"),
        "turnover": Decimal("34000000.00"),
        "city": "Bengaluru",
    },
    {
        "slug": "small",
        "tenant_id": "00000000-0000-4000-8000-000000001102",
        "enterprise_id": "00000000-0000-4000-8000-000000001202",
        "business_id": "biz_gst_small_01",
        "legal_name": "Western Loomworks Private Limited",
        "trade_name": "Western Loomworks",
        "gstin": "27PQRSX5678L1Z2",
        "state_code": "27",
        "classification": "SMALL",
        "investment": Decimal("120000000.00"),
        "turnover": Decimal("420000000.00"),
        "city": "Pune",
    },
    {
        "slug": "medium",
        "tenant_id": "00000000-0000-4000-8000-000000001103",
        "enterprise_id": "00000000-0000-4000-8000-000000001203",
        "business_id": "biz_gst_medium_01",
        "legal_name": "Northline Industrial Systems Limited",
        "trade_name": "Northline Systems",
        "gstin": "07LMNOP9012Q1Z7",
        "state_code": "07",
        "classification": "MEDIUM",
        "investment": Decimal("600000000.00"),
        "turnover": Decimal("2200000000.00"),
        "city": "New Delhi",
    },
]


def stable_id(value: str) -> str:
    return str(uuid5(NAMESPACE, value))


async def seed_demo_data() -> None:
    password_hash = hash_password(get_settings().demo_password.get_secret_value())
    async with session() as db:
        if await db.get(Enterprise, ENTERPRISE_FIXTURES[0]["enterprise_id"]) is not None:
            seeded_users = [
                "user-reviewer",
                *[f"user-{item['slug']}" for item in ENTERPRISE_FIXTURES],
            ]
            for stable_name in seeded_users:
                user = await db.get(User, stable_id(stable_name))
                if user is not None:
                    user.password_hash = password_hash
            return

        reviewer = User(
            id=stable_id("user-reviewer"),
            email="gst.reviewer@gst.demo.xyena.test",
            display_name="Meera Iyer",
            password_hash=password_hash,
            status="ACTIVE",
        )
        db.add(reviewer)

        for position, fixture in enumerate(ENTERPRISE_FIXTURES, start=1):
            enterprise = Enterprise(
                id=fixture["enterprise_id"],
                tenant_id=fixture["tenant_id"],
                business_id=fixture["business_id"],
                legal_name=fixture["legal_name"],
                trade_name=fixture["trade_name"],
                primary_gstin=fixture["gstin"],
                declared_classification=fixture["classification"],
                calculated_classification=fixture["classification"],
                effective_classification=fixture["classification"],
                classification_provenance="UDYAM_TEST_FIXTURE",
                classification_as_of=date(2026, 3, 31),
                status="ACTIVE",
                version=1,
            )
            operator = User(
                id=stable_id(f"user-{fixture['slug']}"),
                email=f"{fixture['slug']}.operator@gst.demo.xyena.test",
                display_name=f"{fixture['trade_name']} Operator",
                password_hash=password_hash,
                status="ACTIVE",
            )
            db.add_all([enterprise, operator])
            await db.flush()
            db.add_all(
                [
                    EnterpriseMembership(
                        id=stable_id(f"membership-{fixture['slug']}-operator"),
                        user_id=operator.id,
                        enterprise_id=enterprise.id,
                        tenant_id=enterprise.tenant_id,
                        roles=["GST_VIEWER", "GST_OPERATOR"],
                    ),
                    EnterpriseMembership(
                        id=stable_id(f"membership-{fixture['slug']}-reviewer"),
                        user_id=reviewer.id,
                        enterprise_id=enterprise.id,
                        tenant_id=enterprise.tenant_id,
                        roles=["GST_VIEWER", "GST_REVIEWER"],
                    ),
                ]
            )
            taxpayer = Taxpayer(
                id=stable_id(f"taxpayer-{fixture['slug']}"),
                tenant_id=enterprise.tenant_id,
                enterprise_id=enterprise.id,
                gstin=enterprise.primary_gstin,
                legal_name=enterprise.legal_name,
                trade_name=enterprise.trade_name,
                taxpayer_type="REGULAR",
                registration_status="ACTIVE",
                registration_date=date(2021, 4, 1) + timedelta(days=position * 90),
                state_code=fixture["state_code"],
                registered_address={
                    "line1": f"{12 + position}, Industrial Estate",
                    "city": fixture["city"],
                    "postal_code": f"5600{position}0",
                },
                risk_flags=[],
                version=1,
            )
            snapshot_body = {
                "enterprise_id": enterprise.id,
                "financial_year": "2025-26",
                "investment": str(fixture["investment"]),
                "turnover": str(fixture["turnover"]),
                "classification": fixture["classification"],
            }
            snapshot = ClassificationSnapshot(
                id=stable_id(f"classification-{fixture['slug']}-2025-26"),
                tenant_id=enterprise.tenant_id,
                enterprise_id=enterprise.id,
                financial_year="2025-26",
                investment_amount=fixture["investment"],
                annual_turnover=fixture["turnover"],
                declared_classification=fixture["classification"],
                calculated_classification=fixture["classification"],
                effective_classification=fixture["classification"],
                source_type="UDYAM_TEST_FIXTURE",
                source_reference=f"udyam_demo_{fixture['slug']}_2025",
                source_hash=canonical_hash(snapshot_body),
                threshold_policy_version=THRESHOLD_VERSION,
                verification_status="VERIFIED",
                effective_from=date(2025, 4, 1),
            )
            db.add_all([taxpayer, snapshot])
            await db.flush()

            invoices = [
                _invoice_fixture(
                    fixture,
                    operator.id,
                    suffix=f"{position}01",
                    status="REGISTERED",
                    days_ago=12 + position,
                    buyer_name="Bluepeak Retail Networks Limited",
                    buyer_gstin="29BUYER1234A1Z8",
                    quantity=Decimal("25"),
                    unit_price=Decimal("18500.00"),
                ),
                _invoice_fixture(
                    fixture,
                    operator.id,
                    suffix=f"{position}02",
                    status="SUBMITTED",
                    days_ago=4 + position,
                    buyer_name="Meridian Procurement Services",
                    buyer_gstin="27BUYER5678B1Z6",
                    quantity=Decimal("12"),
                    unit_price=Decimal("24000.00"),
                ),
                _invoice_fixture(
                    fixture,
                    operator.id,
                    suffix=f"{position}03",
                    status="DRAFT",
                    days_ago=position,
                    buyer_name="Cedar Works India Private Limited",
                    buyer_gstin="07BUYER9012C1Z4",
                    quantity=Decimal("8"),
                    unit_price=Decimal("31250.00"),
                ),
            ]
            for invoice, line, history in invoices:
                db.add_all([invoice, line, history])

            registered = invoices[0][0]
            tax_total = money(
                registered.cgst_amount + registered.sgst_amount + registered.igst_amount
            )
            db.add(
                ReturnSummary(
                    id=stable_id(f"return-{fixture['slug']}-2026-08"),
                    tenant_id=enterprise.tenant_id,
                    enterprise_id=enterprise.id,
                    gstin=enterprise.primary_gstin,
                    period="2026-08",
                    return_type="GSTR1_DEMO",
                    version=1,
                    status="GENERATED",
                    turnover=registered.taxable_value,
                    tax_total=tax_total,
                    invoice_count=1,
                    source_hash=canonical_hash(
                        {"invoice_id": registered.id, "version": registered.version}
                    ),
                )
            )
            db.add(
                AuditEvent(
                    id=stable_id(f"audit-seed-{fixture['slug']}"),
                    tenant_id=enterprise.tenant_id,
                    aggregate_type="ENTERPRISE",
                    aggregate_id=enterprise.id,
                    aggregate_version=1,
                    event_type="demo.enterprise_seeded",
                    actor_type="SYSTEM",
                    actor_id="gst-demo-seeder",
                    reason="Versioned synthetic GST portal seed",
                    metadata_json={"fixture": fixture["slug"]},
                )
            )


def _invoice_fixture(
    fixture: dict[str, object],
    actor_id: str,
    *,
    suffix: str,
    status: str,
    days_ago: int,
    buyer_name: str,
    buyer_gstin: str,
    quantity: Decimal,
    unit_price: Decimal,
) -> tuple[Invoice, InvoiceLine, InvoiceStatusHistory]:
    invoice_date = date.today() - timedelta(days=days_ago)
    intra_state = str(fixture["state_code"]) == buyer_gstin[:2]
    amounts = calculate_line(
        quantity=quantity,
        unit_price=unit_price,
        discount=Decimal("0"),
        gst_rate=Decimal("18"),
        intra_state=intra_state,
    )
    invoice_id = stable_id(f"invoice-{fixture['slug']}-{suffix}")
    invoice_number = f"{str(fixture['slug']).upper()}/26/{suffix}"
    body = {
        "invoice_number": invoice_number,
        "seller_gstin": fixture["gstin"],
        "buyer_gstin": buyer_gstin,
        "total": str(amounts["total_value"]),
    }
    submitted = status in {"SUBMITTED", "REGISTERED", "REJECTED", "CANCELLED"}
    invoice = Invoice(
        id=invoice_id,
        tenant_id=str(fixture["tenant_id"]),
        enterprise_id=str(fixture["enterprise_id"]),
        invoice_number=invoice_number,
        invoice_type="B2B",
        invoice_date=invoice_date,
        financial_year=financial_year(invoice_date),
        seller_gstin=str(fixture["gstin"]),
        buyer_gstin=buyer_gstin,
        buyer_name=buyer_name,
        purchase_order_id=f"PO-DEMO-{suffix}",
        currency="INR",
        place_of_supply=buyer_gstin[:2],
        taxable_value=amounts["taxable_value"],
        cgst_amount=amounts["cgst_amount"],
        sgst_amount=amounts["sgst_amount"],
        igst_amount=amounts["igst_amount"],
        cess_amount=Decimal("0.00"),
        total_invoice_value=amounts["total_value"],
        status=status,
        irn=f"IRNDEMO{canonical_hash(body)[:24].upper()}" if status == "REGISTERED" else None,
        ack_number=f"ACK26{suffix}001" if status == "REGISTERED" else None,
        ack_date=datetime.now(UTC) - timedelta(days=days_ago - 1)
        if status == "REGISTERED"
        else None,
        source_document_hash=canonical_hash(body) if submitted else None,
        security_flags=[],
        version=3 if status == "REGISTERED" else 2 if status == "SUBMITTED" else 1,
        created_by=actor_id,
        updated_by=actor_id,
    )
    line = InvoiceLine(
        id=stable_id(f"line-{fixture['slug']}-{suffix}-1"),
        invoice_id=invoice_id,
        line_number=1,
        description="Synthetic industrial goods",
        hsn_sac="847990",
        quantity=quantity,
        unit="NOS",
        unit_price=unit_price,
        discount=Decimal("0.00"),
        taxable_value=amounts["taxable_value"],
        gst_rate=Decimal("18.00"),
        cgst_amount=amounts["cgst_amount"],
        sgst_amount=amounts["sgst_amount"],
        igst_amount=amounts["igst_amount"],
        total_value=amounts["total_value"],
    )
    history = InvoiceStatusHistory(
        id=stable_id(f"history-{fixture['slug']}-{suffix}-{status}"),
        invoice_id=invoice_id,
        tenant_id=str(fixture["tenant_id"]),
        prior_status=None,
        new_status=status,
        reason="Synthetic seed state",
        actor_id=actor_id,
        version=invoice.version,
    )
    return invoice, line, history
