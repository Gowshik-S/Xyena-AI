from datetime import date
from decimal import Decimal
from uuid import UUID, uuid5

from .auth import hash_password
from .database import session
from .domain import canonical_hash
from .models import (
    AuditEvent,
    Business,
    BusinessAddress,
    BusinessName,
    BusinessPerson,
    BusinessRelationship,
    ChangeRequest,
    OwnershipLink,
    User,
)
from .settings import get_settings


TENANT_ID = "00000000-0000-4000-8000-000000001301"
NAMESPACE = UUID("00000000-0000-4000-8000-000000009903")


def stable_id(value: str) -> str:
    return str(uuid5(NAMESPACE, value))


BUSINESS_FIXTURES = [
    {
        "id": "00000000-0000-4000-8000-000000001201",
        "business_id": "biz_gst_micro_01",
        "registry_number": "U28999KA2021PTC145201",
        "business_type": "COMPANY",
        "legal_name": "Kaveri Precision Components Private Limited",
        "trade_name": "Kaveri Precision",
        "incorporation_date": date(2021, 2, 18),
        "status": "ACTIVE",
        "state": "29",
        "city": "Bengaluru",
        "postal_code": "560058",
        "industry_code": "C2599",
        "classification": "MICRO",
        "gstin": "29ABCDE1234F1Z5",
        "flags": [],
    },
    {
        "id": "00000000-0000-4000-8000-000000002201",
        "business_id": "biz_buyer_bluepeak_01",
        "registry_number": "U52100KA2016PLC092221",
        "business_type": "COMPANY",
        "legal_name": "Bluepeak Retail Networks Limited",
        "trade_name": "Bluepeak Retail",
        "incorporation_date": date(2016, 5, 12),
        "status": "ACTIVE",
        "state": "29",
        "city": "Bengaluru",
        "postal_code": "560103",
        "industry_code": "G4719",
        "classification": "MEDIUM",
        "gstin": "29BUYER1234A1Z8",
        "flags": [],
    },
    {
        "id": "00000000-0000-4000-8000-000000002202",
        "business_id": "biz_supplier_orbit_01",
        "registry_number": "AAE-4421-DEMO",
        "business_type": "LLP",
        "legal_name": "Orbit Alloy Services LLP",
        "trade_name": "Orbit Alloy",
        "incorporation_date": date(2019, 11, 6),
        "status": "SUSPENDED",
        "state": "27",
        "city": "Pune",
        "postal_code": "411019",
        "industry_code": "C2410",
        "classification": "SMALL",
        "gstin": "27ORBIT4421L1Z3",
        "flags": ["GST_STATUS_MISMATCH", "RELATED_PARTY_REVIEW"],
    },
    {
        "id": "00000000-0000-4000-8000-000000002203",
        "business_id": "biz_pending_nimbus_01",
        "registry_number": "U62099DL2026PTC441902",
        "business_type": "COMPANY",
        "legal_name": "Nimbus Trade Systems Private Limited",
        "trade_name": "Nimbus Trade",
        "incorporation_date": date(2026, 6, 9),
        "status": "PENDING_REVIEW",
        "state": "07",
        "city": "New Delhi",
        "postal_code": "110020",
        "industry_code": "J6209",
        "classification": "MICRO",
        "gstin": "07NIMBU4419N1Z6",
        "flags": ["NEWLY_INCORPORATED"],
    },
]


async def seed_demo_data() -> None:
    settings = get_settings()
    async with session() as db:
        if await db.get(Business, BUSINESS_FIXTURES[0]["id"]) is not None:
            return
        operator = User(
            id=stable_id("registry-operator"), tenant_id=TENANT_ID,
            email="operator@registry.demo.xyena.test", display_name="Ananya Rao",
            password_hash=hash_password(settings.operator_password.get_secret_value()),
            roles=["REGISTRY_VIEWER", "REGISTRY_OPERATOR"], status="ACTIVE",
        )
        reviewer = User(
            id=stable_id("registry-reviewer"), tenant_id=TENANT_ID,
            email="reviewer@registry.demo.xyena.test", display_name="Vikram Menon",
            password_hash=hash_password(settings.reviewer_password.get_secret_value()),
            roles=["REGISTRY_VIEWER", "REGISTRY_REVIEWER"], status="ACTIVE",
        )
        db.add_all([operator, reviewer])
        for index, fixture in enumerate(BUSINESS_FIXTURES, start=1):
            address = {
                "line1": f"{18 + index}, Industrial Records Estate",
                "city": fixture["city"], "state_code": fixture["state"],
                "postal_code": fixture["postal_code"], "country": "IN",
            }
            source = {
                "registry_number": fixture["registry_number"], "legal_name": fixture["legal_name"],
                "status": fixture["status"], "gstin": fixture["gstin"], "address": address,
            }
            business = Business(
                id=fixture["id"], tenant_id=TENANT_ID, business_id=fixture["business_id"],
                registry_number=fixture["registry_number"], business_type=fixture["business_type"],
                legal_name=fixture["legal_name"], trade_name=fixture["trade_name"],
                incorporation_date=fixture["incorporation_date"], status=fixture["status"],
                registered_state_code=fixture["state"], registered_address=address,
                industry_code=fixture["industry_code"], msme_classification=fixture["classification"],
                primary_gstin=fixture["gstin"], pan_token=f"pan_demo_{index:02d}",
                risk_flags=fixture["flags"], source_hash=canonical_hash(source), version=1,
                created_by=operator.id, updated_by=operator.id,
            )
            db.add(business)
            db.add_all([
                BusinessName(
                    id=stable_id(f"name-{index}"), tenant_id=TENANT_ID, business_id=business.id,
                    name_type="LEGAL", name=business.legal_name,
                    effective_from=business.incorporation_date, source_hash=canonical_hash(business.legal_name),
                    record_version=1,
                ),
                BusinessAddress(
                    id=stable_id(f"address-{index}"), tenant_id=TENANT_ID, business_id=business.id,
                    address_type="REGISTERED", address_json=address, verification_status="VERIFIED",
                    effective_from=business.incorporation_date, source_hash=canonical_hash(address),
                    record_version=1,
                ),
                BusinessPerson(
                    id=stable_id(f"person-{index}"), tenant_id=TENANT_ID, business_id=business.id,
                    person_token=f"person_demo_{index:02d}", display_name=["Priya Nair", "Arjun Shah", "Rohit Kulkarni", "Neha Batra"][index - 1],
                    role="AUTHORIZED_SIGNATORY", appointment_date=business.incorporation_date,
                    authorization_status="ACTIVE" if business.status == "ACTIVE" else "REVIEW_REQUIRED",
                    verification_status="VERIFIED", source_hash=canonical_hash({"business": business.id, "person": index}), version=1,
                ),
                OwnershipLink(
                    id=stable_id(f"owner-{index}"), tenant_id=TENANT_ID, business_id=business.id,
                    owner_type="PERSON", owner_token=f"owner_demo_{index:02d}",
                    owner_display_name=["Priya Nair", "Arjun Shah", "Rohit Kulkarni", "Neha Batra"][index - 1],
                    ownership_percentage=Decimal("70.00"), effective_from=business.incorporation_date,
                    verification_status="VERIFIED", source_hash=canonical_hash({"business": business.id, "owner": index}), version=1,
                ),
            ])
            db.add(AuditEvent(
                id=stable_id(f"audit-business-{index}"), tenant_id=TENANT_ID,
                aggregate_type="BUSINESS", aggregate_id=business.id, aggregate_version=1,
                event_type="demo.business_seeded", actor_type="SYSTEM", actor_id="registry-demo-seeder",
                reason="Versioned synthetic registry fixture", metadata_json={"fixture": index},
            ))
        db.add_all([
            BusinessRelationship(
                id=stable_id("relationship-kaveri-bluepeak"), tenant_id=TENANT_ID,
                source_business_id=BUSINESS_FIXTURES[0]["id"], target_business_id=BUSINESS_FIXTURES[1]["id"],
                relationship_type="BUYER", status="ACTIVE", effective_from=date(2023, 4, 1),
                evidence_hash=canonical_hash("kaveri-bluepeak-buyer"), version=1,
            ),
            BusinessRelationship(
                id=stable_id("relationship-orbit-bluepeak"), tenant_id=TENANT_ID,
                source_business_id=BUSINESS_FIXTURES[2]["id"], target_business_id=BUSINESS_FIXTURES[1]["id"],
                relationship_type="BUYER", status="REVOKED", effective_from=date(2022, 7, 1),
                effective_to=date(2026, 5, 31), evidence_hash=canonical_hash("orbit-bluepeak-revoked"), version=2,
            ),
            ChangeRequest(
                id=stable_id("pending-change-kaveri"), tenant_id=TENANT_ID,
                business_id=BUSINESS_FIXTURES[0]["id"], target_version=1,
                requested_patch={"trade_name": "Kaveri Precision Works"},
                reason="Trade name alignment requested for current commercial records",
                status="SUBMITTED", requested_by=operator.id,
            ),
        ])
