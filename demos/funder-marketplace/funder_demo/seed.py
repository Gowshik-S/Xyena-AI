import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from .database import session
from .models import (
    AuditEvent,
    FunderInstitution,
    FundingApplication,
    FundingCommitment,
    FundingOffer,
    FundingProgram,
    OfferReservation,
    OutboxEvent,
    ProgramRule,
)


DEMO_TENANT_ID = "00000000-0000-4000-8000-000000000101"
DEMO_ORGANIZATION_ID = "00000000-0000-4000-8000-000000000301"
DEMO_USER_ID = "00000000-0000-4000-8000-000000000201"


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


async def seed_demo_data() -> None:
    async with session() as db:
        if await db.get(FunderInstitution, "funder_demo_aurum") is not None:
            return

        funders = [
            FunderInstitution(
                id="funder_demo_aurum",
                tenant_id=DEMO_TENANT_ID,
                legal_name="Aurum Working Capital Private Limited",
                display_name="Aurum Capital",
                institution_type="NBFC",
                status="ACTIVE",
                supported_currencies=["INR"],
                supported_rails=["BANK_TRANSFER", "ESCROW"],
                settlement_account_token="acct_tok_aurum_demo_81",
                policy_metadata={"review_sla_hours": 4, "risk_band_max": "B"},
                version=3,
            ),
            FunderInstitution(
                id="funder_demo_summit",
                tenant_id=DEMO_TENANT_ID,
                legal_name="Summit Trade Finance Limited",
                display_name="Summit Trade",
                institution_type="TRADE_FINANCE",
                status="ACTIVE",
                supported_currencies=["INR"],
                supported_rails=["BANK_TRANSFER"],
                settlement_account_token="acct_tok_summit_demo_44",
                policy_metadata={"review_sla_hours": 8, "risk_band_max": "B"},
                version=2,
            ),
            FunderInstitution(
                id="funder_demo_civic",
                tenant_id=DEMO_TENANT_ID,
                legal_name="Civic Cooperative Credit Society",
                display_name="Civic Cooperative",
                institution_type="COOPERATIVE",
                status="ACTIVE",
                supported_currencies=["INR"],
                supported_rails=["BANK_TRANSFER"],
                settlement_account_token="acct_tok_civic_demo_19",
                policy_metadata={"review_sla_hours": 12, "risk_band_max": "A"},
                version=1,
            ),
        ]
        db.add_all(funders)
        await db.flush()

        today = date.today()
        programs = [
            FundingProgram(
                id="program_demo_rapid70",
                tenant_id=DEMO_TENANT_ID,
                funder_id=funders[0].id,
                program_code="RAPID-70",
                name="Rapid Receivable 70",
                product_type="INVOICE_FINANCE",
                currency="INR",
                minimum_amount=Decimal("100000"),
                maximum_amount=Decimal("5000000"),
                total_capacity=Decimal("25000000"),
                reserved_capacity=Decimal("1200000"),
                committed_capacity=Decimal("6400000"),
                advance_rate_maximum=Decimal("70"),
                tenor_minimum_days=15,
                tenor_maximum_days=90,
                pricing_model={"annual_rate_from": "13.25", "fee_percent": "0.75"},
                eligible_regions=["Karnataka", "Tamil Nadu", "Maharashtra"],
                eligible_industries=["Manufacturing", "Textiles", "Components"],
                required_evidence_types=["GST_INVOICE", "ERP_ACCEPTANCE", "DELIVERY"],
                effective_from=today - timedelta(days=120),
                status="ACTIVE",
                policy_version=4,
                version=6,
            ),
            FundingProgram(
                id="program_demo_tradeplus",
                tenant_id=DEMO_TENANT_ID,
                funder_id=funders[1].id,
                program_code="TRADE-PLUS",
                name="Trade Plus 65",
                product_type="SUPPLY_CHAIN_FINANCE",
                currency="INR",
                minimum_amount=Decimal("250000"),
                maximum_amount=Decimal("8000000"),
                total_capacity=Decimal("40000000"),
                reserved_capacity=Decimal("1800000"),
                committed_capacity=Decimal("12400000"),
                advance_rate_maximum=Decimal("65"),
                tenor_minimum_days=30,
                tenor_maximum_days=120,
                pricing_model={"annual_rate_from": "12.50", "fee_percent": "1.10"},
                eligible_regions=["Karnataka", "Gujarat", "Maharashtra"],
                eligible_industries=["Manufacturing", "Engineering", "Logistics"],
                required_evidence_types=["GST_INVOICE", "ERP_ACCEPTANCE", "BANK_EVIDENCE"],
                effective_from=today - timedelta(days=80),
                status="ACTIVE",
                policy_version=3,
                version=5,
            ),
            FundingProgram(
                id="program_demo_local60",
                tenant_id=DEMO_TENANT_ID,
                funder_id=funders[2].id,
                program_code="LOCAL-60",
                name="Local Enterprise 60",
                product_type="INVOICE_DISCOUNTING",
                currency="INR",
                minimum_amount=Decimal("50000"),
                maximum_amount=Decimal("2000000"),
                total_capacity=Decimal("10000000"),
                reserved_capacity=Decimal("0"),
                committed_capacity=Decimal("4800000"),
                advance_rate_maximum=Decimal("60"),
                tenor_minimum_days=15,
                tenor_maximum_days=60,
                pricing_model={"annual_rate_from": "11.75", "fee_percent": "0.50"},
                eligible_regions=["Karnataka"],
                eligible_industries=["Manufacturing", "Services"],
                required_evidence_types=["GST_INVOICE", "ERP_ACCEPTANCE"],
                effective_from=today - timedelta(days=45),
                status="SUSPENDED",
                policy_version=2,
                version=4,
            ),
        ]
        db.add_all(programs)
        await db.flush()
        db.add_all(
            [
                ProgramRule(
                    id="rule_demo_rapid_region",
                    program_id=programs[0].id,
                    rule_key="region_allowed",
                    input_field="region",
                    operator="IN",
                    comparison_value=programs[0].eligible_regions,
                    reason_code="REGION_NOT_ELIGIBLE",
                    effective_from=programs[0].effective_from,
                    version=4,
                ),
                ProgramRule(
                    id="rule_demo_rapid_amount",
                    program_id=programs[0].id,
                    rule_key="amount_within_program",
                    input_field="requested_amount",
                    operator="BETWEEN",
                    comparison_value=["100000", "5000000"],
                    reason_code="AMOUNT_OUTSIDE_PROGRAM",
                    effective_from=programs[0].effective_from,
                    version=4,
                ),
                ProgramRule(
                    id="rule_demo_trade_industry",
                    program_id=programs[1].id,
                    rule_key="industry_allowed",
                    input_field="industry",
                    operator="IN",
                    comparison_value=programs[1].eligible_industries,
                    reason_code="INDUSTRY_NOT_ELIGIBLE",
                    effective_from=programs[1].effective_from,
                    version=3,
                ),
            ]
        )

        now = datetime.now(UTC)
        applications = [
            FundingApplication(
                id="application_demo_7001",
                tenant_id=DEMO_TENANT_ID,
                case_id="case_demo_1023",
                msme_id="msme_demo_northstar",
                msme_name="Northstar Precision Components",
                receivable_id="receivable_demo_inv2041",
                requested_amount=Decimal("400000"),
                currency="INR",
                tenor_days=60,
                region="Karnataka",
                industry="Manufacturing",
                evidence_receipt_ids=["evr_gst_2041", "evr_erp_2041", "evr_delivery_501"],
                exposure_snapshot_reference="exposure_demo_northstar_v4",
                exposure_amount=Decimal("1100000"),
                eligibility_results=[{"program_id": "program_demo_rapid70", "eligible": True}],
                status="APPROVED",
                submitted_at=now - timedelta(days=4),
                reviewed_by="reviewer_demo_aurum",
                version=3,
            ),
            FundingApplication(
                id="application_demo_7008",
                tenant_id=DEMO_TENANT_ID,
                case_id="case_demo_1092",
                msme_id="msme_demo_western",
                msme_name="Western Loomworks Private Limited",
                receivable_id="receivable_demo_inv3308",
                requested_amount=Decimal("850000"),
                currency="INR",
                tenor_days=75,
                region="Karnataka",
                industry="Textiles",
                evidence_receipt_ids=["evr_gst_3308", "evr_erp_3308"],
                exposure_snapshot_reference="exposure_demo_western_v2",
                exposure_amount=Decimal("320000"),
                eligibility_results=[],
                status="UNDER_REVIEW",
                submitted_at=now - timedelta(hours=9),
                version=2,
            ),
            FundingApplication(
                id="application_demo_7011",
                tenant_id=DEMO_TENANT_ID,
                case_id="case_demo_1104",
                msme_id="msme_demo_civicfield",
                msme_name="Civic Field Services LLP",
                receivable_id="receivable_demo_inv2099",
                requested_amount=Decimal("175000"),
                currency="INR",
                tenor_days=45,
                region="Karnataka",
                industry="Services",
                evidence_receipt_ids=["evr_gst_2099"],
                exposure_snapshot_reference="exposure_demo_civicfield_v1",
                exposure_amount=Decimal("0"),
                eligibility_results=[{"eligible": False, "reason": "ERP_ACCEPTANCE_MISSING"}],
                status="DECLINED",
                submitted_at=now - timedelta(days=1),
                reviewed_by="reviewer_demo_civic",
                version=3,
            ),
        ]
        db.add_all(applications)
        await db.flush()

        offers = [
            FundingOffer(
                id="offer_demo_8101",
                tenant_id=DEMO_TENANT_ID,
                application_id=applications[0].id,
                funder_id=funders[0].id,
                program_id=programs[0].id,
                approved_amount=Decimal("400000"),
                advance_rate=Decimal("67.80"),
                annual_rate=Decimal("13.25"),
                fee_amount=Decimal("3000"),
                tenor_days=60,
                repayment_terms="Single settlement on buyer payment or day 60",
                conditions=["Buyer acceptance remains valid", "No duplicate financing"],
                expires_at=now + timedelta(days=2),
                status="RESERVED",
                offer_hash=_hash(["offer_demo_8101", "400000", "13.25", 60]),
                version=3,
            ),
            FundingOffer(
                id="offer_demo_8102",
                tenant_id=DEMO_TENANT_ID,
                application_id=applications[0].id,
                funder_id=funders[1].id,
                program_id=programs[1].id,
                approved_amount=Decimal("383500"),
                advance_rate=Decimal("65.00"),
                annual_rate=Decimal("12.50"),
                fee_amount=Decimal("4218.50"),
                tenor_days=60,
                repayment_terms="Single settlement on buyer payment or day 60",
                conditions=["Bank evidence refreshed before commitment"],
                expires_at=now + timedelta(days=1),
                status="ISSUED",
                offer_hash=_hash(["offer_demo_8102", "383500", "12.50", 60]),
                version=2,
            ),
            FundingOffer(
                id="offer_demo_8110",
                tenant_id=DEMO_TENANT_ID,
                application_id=applications[1].id,
                funder_id=funders[0].id,
                program_id=programs[0].id,
                approved_amount=Decimal("595000"),
                advance_rate=Decimal("70.00"),
                annual_rate=Decimal("14.10"),
                fee_amount=Decimal("4462.50"),
                tenor_days=75,
                repayment_terms="Single settlement on buyer payment or day 75",
                conditions=["Delivery receipt required before reservation"],
                expires_at=now - timedelta(hours=3),
                status="EXPIRED",
                offer_hash=_hash(["offer_demo_8110", "595000", "14.10", 75]),
                version=3,
            ),
        ]
        db.add_all(offers)
        await db.flush()

        reservation = OfferReservation(
            id="reservation_demo_9001",
            tenant_id=DEMO_TENANT_ID,
            offer_id=offers[0].id,
            program_id=programs[0].id,
            reserved_amount=Decimal("400000"),
            case_id=applications[0].case_id,
            msme_id=applications[0].msme_id,
            expires_at=now + timedelta(hours=18),
            idempotency_key="reserve_demo_case1023_offer8101",
            status="ACTIVE",
            version=2,
        )
        db.add(reservation)
        await db.flush()
        commitment = FundingCommitment(
            id="commitment_demo_9501",
            tenant_id=DEMO_TENANT_ID,
            reservation_id=reservation.id,
            committed_amount=Decimal("400000"),
            action_hash=_hash(
                {
                    "reservation_id": reservation.id,
                    "amount": "400000.00",
                    "destination_token": "beneficiary_tok_northstar_demo_17",
                }
            ),
            destination_token="beneficiary_tok_northstar_demo_17",
            status="PREPARED",
            settlement_status="PENDING",
            version=1,
        )
        db.add(commitment)

        audit_rows = [
            ("audit_demo_application", "FundingApplication", applications[0].id, 3, "application.approved", "reviewer_demo_aurum", now - timedelta(days=3)),
            ("audit_demo_offer", "FundingOffer", offers[0].id, 2, "offer.issued", "operator_demo_aurum", now - timedelta(days=2)),
            ("audit_demo_reservation", "OfferReservation", reservation.id, 2, "offer.reserved", "xyena-supervisor", now - timedelta(hours=6)),
            ("audit_demo_commitment", "FundingCommitment", commitment.id, 1, "commitment.prepared", "xyena-supervisor", now - timedelta(hours=2)),
        ]
        db.add_all(
            [
                AuditEvent(
                    id=row[0], tenant_id=DEMO_TENANT_ID, aggregate_type=row[1],
                    aggregate_id=row[2], aggregate_version=row[3], event_type=row[4],
                    actor_type="AGENT" if row[5] == "xyena-supervisor" else "USER",
                    actor_id=row[5], reason="Synthetic marketplace workflow",
                    payload={}, correlation_id=f"corr_{row[0]}", occurred_at=row[6],
                )
                for row in audit_rows
            ]
        )
        db.add(
            OutboxEvent(
                id="outbox_demo_commitment", tenant_id=DEMO_TENANT_ID,
                aggregate_type="FundingCommitment", aggregate_id=commitment.id,
                aggregate_version=1, event_type="commitment.prepared",
                payload={"commitment_id": commitment.id},
                correlation_id="corr_audit_demo_commitment", attempt_count=0,
            )
        )

