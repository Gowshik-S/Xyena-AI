import hashlib
import hmac
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import session
from .models import (
    AuditEvent,
    FunderInstitution,
    FundingApplication,
    FundingCommitment,
    FundingOffer,
    FundingProgram,
    InboxEvent,
    OfferReservation,
    OutboxEvent,
    ProgramRule,
)
from .schemas import (
    ApplicationRequest,
    CommitmentConfirmRequest,
    CommitmentPrepareRequest,
    ExternalEventEnvelope,
    OfferRequest,
    ProgramTransitionRequest,
    ReleaseRequest,
    ReserveRequest,
    ReviewRequest,
)
from .settings import get_settings


class FunderDomainError(RuntimeError):
    pass


class FunderNotFoundError(FunderDomainError):
    pass


class FunderConflictError(FunderDomainError):
    pass


class FunderService:
    async def dashboard(self, tenant_id: str) -> dict[str, Any]:
        async with session() as db:
            funders = (await db.scalars(select(FunderInstitution).where(FunderInstitution.tenant_id == tenant_id).order_by(FunderInstitution.display_name))).all()
            programs = (await db.scalars(select(FundingProgram).where(FundingProgram.tenant_id == tenant_id).order_by(FundingProgram.name))).all()
            applications = (await db.scalars(select(FundingApplication).where(FundingApplication.tenant_id == tenant_id).order_by(FundingApplication.submitted_at.desc()))).all()
            offers = (await db.scalars(select(FundingOffer).where(FundingOffer.tenant_id == tenant_id).order_by(FundingOffer.created_at.desc()))).all()
            reservations = (await db.scalars(select(OfferReservation).where(OfferReservation.tenant_id == tenant_id).order_by(OfferReservation.created_at.desc()))).all()
            commitments = (await db.scalars(select(FundingCommitment).where(FundingCommitment.tenant_id == tenant_id).order_by(FundingCommitment.created_at.desc()))).all()
            audits = (await db.scalars(select(AuditEvent).where(AuditEvent.tenant_id == tenant_id).order_by(AuditEvent.occurred_at.desc()).limit(30))).all()
            rules = (await db.scalars(select(ProgramRule))).all()
            pending_outbox = await db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.tenant_id == tenant_id, OutboxEvent.published_at.is_(None)))

        funder_map = {value.id: value for value in funders}
        application_map = {value.id: value for value in applications}
        program_map = {value.id: value for value in programs}
        reservation_map = {value.id: value for value in reservations}
        rules_by_program: dict[str, list[ProgramRule]] = {}
        for rule in rules:
            rules_by_program.setdefault(rule.program_id, []).append(rule)
        return {
            "environment": "SYNTHETIC_NON_PRODUCTION",
            "tenant_id": tenant_id,
            "summary": {
                "active_programs": sum(value.status == "ACTIVE" for value in programs),
                "available_capacity": str(sum((self._available(value) for value in programs if value.status == "ACTIVE"), Decimal("0"))),
                "applications_under_review": sum(value.status in {"RECEIVED", "ELIGIBILITY_CHECKED", "UNDER_REVIEW"} for value in applications),
                "live_offers": sum(value.status in {"ISSUED", "RESERVED"} for value in offers),
                "active_reservations": sum(value.status == "ACTIVE" for value in reservations),
                "committed_value": str(sum((value.committed_amount for value in commitments if value.status in {"COMMITTED", "DISBURSED", "SETTLED"}), Decimal("0"))),
                "pending_outbox_events": pending_outbox or 0,
            },
            "funders": [self._funder(value) for value in funders],
            "programs": [self._program(value, funder_map.get(value.funder_id), rules_by_program.get(value.id, [])) for value in programs],
            "applications": [self._application(value) for value in applications],
            "offers": [self._offer(value, funder_map.get(value.funder_id), program_map.get(value.program_id), application_map.get(value.application_id)) for value in offers],
            "reservations": [self._reservation(value) for value in reservations],
            "commitments": [self._commitment(value, reservation_map.get(value.reservation_id)) for value in commitments],
            "audit_events": [self._audit(value) for value in audits],
        }

    async def search_programs(
        self,
        tenant_id: str,
        amount: Decimal,
        tenor_days: int,
        region: str,
        industry: str,
    ) -> dict[str, Any]:
        async with session() as db:
            values = (await db.scalars(select(FundingProgram).where(FundingProgram.tenant_id == tenant_id, FundingProgram.status == "ACTIVE"))).all()
            funders = {value.id: value for value in (await db.scalars(select(FunderInstitution).where(FunderInstitution.tenant_id == tenant_id))).all()}
        eligible = []
        rejected = []
        for value in values:
            reasons = self._eligibility_reasons(value, amount, tenor_days, region, industry)
            projection = self._program(value, funders.get(value.funder_id), [])
            if reasons:
                rejected.append({"program_id": value.id, "reason_codes": reasons})
            else:
                eligible.append(projection)
        return {"eligible_programs": eligible, "rejected_programs": rejected, "evaluated_at": datetime.now(UTC).isoformat()}

    async def create_application(
        self, tenant_id: str, body: ApplicationRequest, actor: str, correlation_id: str
    ) -> dict[str, Any]:
        async with session() as db:
            if await db.scalar(select(FundingApplication).where(FundingApplication.tenant_id == tenant_id, FundingApplication.case_id == body.case_id)):
                raise FunderConflictError("A marketplace application already exists for this case.")
            programs = (await db.scalars(select(FundingProgram).where(FundingProgram.tenant_id == tenant_id, FundingProgram.status == "ACTIVE"))).all()
            results = []
            for program in programs:
                reasons = self._eligibility_reasons(program, body.requested_amount, body.tenor_days, body.region, body.industry)
                results.append({"program_id": program.id, "eligible": not reasons, "reason_codes": reasons, "policy_version": program.policy_version})
            value = FundingApplication(
                id=f"application_demo_{uuid4().hex[:14]}", tenant_id=tenant_id,
                case_id=body.case_id, msme_id=body.msme_id, msme_name=body.msme_name,
                receivable_id=body.receivable_id, requested_amount=body.requested_amount,
                currency=body.currency, tenor_days=body.tenor_days, region=body.region,
                industry=body.industry, evidence_receipt_ids=body.evidence_receipt_ids,
                exposure_snapshot_reference=body.exposure_snapshot_reference,
                exposure_amount=body.exposure_amount, eligibility_results=results,
                status="ELIGIBILITY_CHECKED", submitted_at=datetime.now(UTC), version=1,
            )
            db.add(value)
            self._record(db, value, "application.eligibility_checked", actor, correlation_id, {"eligible_programs": sum(result["eligible"] for result in results)})
            return self._application(value)

    async def review_application(
        self, tenant_id: str, application_id: str, expected_version: int,
        body: ReviewRequest, correlation_id: str,
    ) -> dict[str, Any]:
        async with session() as db:
            value = await self._application_model(db, tenant_id, application_id, lock=True)
            self._expect_version(value.version, expected_version)
            if value.status not in {"ELIGIBILITY_CHECKED", "UNDER_REVIEW"}:
                raise FunderDomainError("Only an eligibility-checked application can be reviewed.")
            if body.decision == "APPROVE" and not any(result.get("eligible") for result in value.eligibility_results):
                raise FunderDomainError("Application has no eligible active funding program.")
            value.status = "APPROVED" if body.decision == "APPROVE" else "DECLINED"
            value.reviewed_by = body.actor
            value.version += 1
            self._record(db, value, f"application.{value.status.lower()}", body.actor, correlation_id, {"reason": body.reason})
            return self._application(value)

    async def issue_offer(
        self, tenant_id: str, application_id: str, expected_version: int,
        body: OfferRequest, correlation_id: str,
    ) -> dict[str, Any]:
        async with session() as db:
            application = await self._application_model(db, tenant_id, application_id, lock=True)
            self._expect_version(application.version, expected_version)
            if application.status != "APPROVED":
                raise FunderDomainError("Offers require an approved funding application.")
            program = await self._program_model(db, tenant_id, body.program_id, lock=True)
            if program.status != "ACTIVE":
                raise FunderDomainError("The selected program is not active.")
            if body.approved_amount > application.requested_amount or body.approved_amount > program.maximum_amount:
                raise FunderDomainError("Offer exceeds the application or program amount bound.")
            if body.advance_rate > program.advance_rate_maximum:
                raise FunderDomainError("Offer advance rate exceeds the active program policy.")
            if not program.tenor_minimum_days <= body.tenor_days <= program.tenor_maximum_days:
                raise FunderDomainError("Offer tenor is outside the active program range.")
            if self._utc(body.expires_at) <= datetime.now(UTC):
                raise FunderDomainError("Offer expiry must be in the future.")
            canonical = {
                "application_id": application.id, "program_id": program.id,
                "amount": str(body.approved_amount), "annual_rate": str(body.annual_rate),
                "fee_amount": str(body.fee_amount), "tenor_days": body.tenor_days,
                "expires_at": body.expires_at.isoformat(),
            }
            value = FundingOffer(
                id=f"offer_demo_{uuid4().hex[:14]}", tenant_id=tenant_id,
                application_id=application.id, funder_id=program.funder_id, program_id=program.id,
                approved_amount=body.approved_amount, advance_rate=body.advance_rate,
                annual_rate=body.annual_rate, fee_amount=body.fee_amount,
                tenor_days=body.tenor_days, repayment_terms=body.repayment_terms,
                conditions=body.conditions, expires_at=body.expires_at,
                status="ISSUED", offer_hash=self._hash(canonical), version=1,
            )
            db.add(value)
            application.version += 1
            self._record(db, value, "offer.issued", body.actor, correlation_id, {"application_id": application.id, "offer_hash": value.offer_hash})
            return self._offer(value, None, program, application)

    async def reserve_offer(
        self, tenant_id: str, offer_id: str, body: ReserveRequest,
        actor: str, correlation_id: str,
    ) -> dict[str, Any]:
        async with session() as db:
            existing = await db.scalar(select(OfferReservation).where(OfferReservation.tenant_id == tenant_id, OfferReservation.idempotency_key == body.idempotency_key))
            if existing is not None:
                if existing.offer_id != offer_id or existing.reserved_amount != body.amount:
                    raise FunderConflictError("Idempotency key was already used for another reservation request.")
                return self._reservation(existing)
            offer = await self._offer_model(db, tenant_id, offer_id, lock=True)
            if offer.status != "ISSUED" or self._utc(offer.expires_at) <= datetime.now(UTC):
                raise FunderDomainError("Only a current issued offer can be reserved.")
            if body.amount > offer.approved_amount:
                raise FunderDomainError("Reservation exceeds the approved offer amount.")
            application = await self._application_model(db, tenant_id, offer.application_id)
            program = await self._program_model(db, tenant_id, offer.program_id, lock=True)
            if program.status != "ACTIVE" or body.amount > self._available(program):
                raise FunderConflictError("Program capacity is no longer available.")
            if self._utc(body.expires_at) <= datetime.now(UTC) or self._utc(body.expires_at) > self._utc(offer.expires_at):
                raise FunderDomainError("Reservation expiry must be current and no later than the offer expiry.")
            value = OfferReservation(
                id=f"reservation_demo_{uuid4().hex[:14]}", tenant_id=tenant_id,
                offer_id=offer.id, program_id=program.id, reserved_amount=body.amount,
                case_id=application.case_id, msme_id=application.msme_id,
                expires_at=body.expires_at, idempotency_key=body.idempotency_key,
                status="ACTIVE", version=1,
            )
            db.add(value)
            program.reserved_capacity += body.amount
            program.version += 1
            offer.status = "RESERVED"
            offer.version += 1
            self._record(db, value, "offer.reserved", actor, correlation_id, {"program_id": program.id, "reserved_amount": str(body.amount)})
            return self._reservation(value)

    async def release_reservation(
        self, tenant_id: str, reservation_id: str, expected_version: int,
        body: ReleaseRequest, correlation_id: str,
    ) -> dict[str, Any]:
        async with session() as db:
            value = await self._reservation_model(db, tenant_id, reservation_id, lock=True)
            self._expect_version(value.version, expected_version)
            if value.status != "ACTIVE":
                raise FunderDomainError("Only an active reservation can be released.")
            program = await self._program_model(db, tenant_id, value.program_id, lock=True)
            offer = await self._offer_model(db, tenant_id, value.offer_id, lock=True)
            program.reserved_capacity = max(Decimal("0"), program.reserved_capacity - value.reserved_amount)
            program.version += 1
            offer.status = "ISSUED" if self._utc(offer.expires_at) > datetime.now(UTC) else "EXPIRED"
            offer.version += 1
            value.status = "RELEASED"
            value.release_reference = f"release_demo_{uuid4().hex[:12]}"
            value.version += 1
            self._record(db, value, "reservation.released", body.actor, correlation_id, {"reason": body.reason})
            return self._reservation(value)

    async def prepare_commitment(
        self, tenant_id: str, reservation_id: str, body: CommitmentPrepareRequest,
        actor: str, correlation_id: str,
    ) -> dict[str, Any]:
        async with session() as db:
            reservation = await self._reservation_model(db, tenant_id, reservation_id, lock=True)
            if reservation.status != "ACTIVE" or self._utc(reservation.expires_at) <= datetime.now(UTC):
                raise FunderDomainError("Commitment preparation requires a current active reservation.")
            existing = await db.scalar(select(FundingCommitment).where(FundingCommitment.reservation_id == reservation.id))
            if existing is not None:
                return self._commitment(existing, reservation)
            canonical = self._commitment_action(reservation.id, reservation.reserved_amount, body.destination_token)
            value = FundingCommitment(
                id=f"commitment_demo_{uuid4().hex[:14]}", tenant_id=tenant_id,
                reservation_id=reservation.id, committed_amount=reservation.reserved_amount,
                action_hash=self._hash(canonical), destination_token=body.destination_token,
                status="PREPARED", settlement_status="PENDING", version=1,
            )
            db.add(value)
            self._record(db, value, "commitment.prepared", actor, correlation_id, {"action_hash": value.action_hash, "reservation_id": reservation.id})
            return self._commitment(value, reservation)

    async def confirm_commitment(
        self, tenant_id: str, commitment_id: str, body: CommitmentConfirmRequest,
        actor: str, correlation_id: str,
    ) -> dict[str, Any]:
        async with session() as db:
            value = await self._commitment_model(db, tenant_id, commitment_id, lock=True)
            if value.status == "COMMITTED" and value.execution_reference == body.execution_reference:
                reservation = await self._reservation_model(db, tenant_id, value.reservation_id)
                return self._commitment(value, reservation)
            if value.status != "PREPARED":
                raise FunderDomainError("Only a prepared commitment can be confirmed.")
            if not hmac.compare_digest(value.action_hash, body.action_hash):
                raise FunderConflictError("Guardian action hash does not match the prepared commitment.")
            reservation = await self._reservation_model(db, tenant_id, value.reservation_id, lock=True)
            if reservation.status != "ACTIVE" or self._utc(reservation.expires_at) <= datetime.now(UTC):
                raise FunderDomainError("Reservation expired before commitment confirmation.")
            program = await self._program_model(db, tenant_id, reservation.program_id, lock=True)
            program.reserved_capacity = max(Decimal("0"), program.reserved_capacity - value.committed_amount)
            program.committed_capacity += value.committed_amount
            program.version += 1
            reservation.status = "COMMITTED"
            reservation.commit_reference = value.id
            reservation.version += 1
            value.guardian_authorization_id = body.guardian_authorization_id
            value.execution_reference = body.execution_reference
            value.status = "COMMITTED"
            value.version += 1
            self._record(db, value, "commitment.confirmed", actor, correlation_id, {"guardian_authorization_id": body.guardian_authorization_id, "execution_reference": body.execution_reference})
            return self._commitment(value, reservation)

    async def transition_program(
        self, tenant_id: str, program_id: str, expected_version: int,
        body: ProgramTransitionRequest, correlation_id: str,
    ) -> dict[str, Any]:
        transitions = {
            ("DRAFT", "ACTIVATE"): "ACTIVE", ("SUSPENDED", "ACTIVATE"): "ACTIVE",
            ("ACTIVE", "SUSPEND"): "SUSPENDED", ("ACTIVE", "CLOSE"): "CLOSED",
            ("SUSPENDED", "CLOSE"): "CLOSED",
        }
        async with session() as db:
            value = await self._program_model(db, tenant_id, program_id, lock=True)
            self._expect_version(value.version, expected_version)
            target = transitions.get((value.status, body.action))
            if target is None:
                raise FunderDomainError(f"Program cannot transition from {value.status} using {body.action}.")
            value.status = target
            value.version += 1
            self._record(db, value, f"program.{target.lower()}", body.actor, correlation_id, {"reason": body.reason})
            return self._program(value, None, [])

    async def get_offer(self, tenant_id: str, offer_id: str) -> dict[str, Any]:
        async with session() as db:
            value = await self._offer_model(db, tenant_id, offer_id)
            funder = await db.get(FunderInstitution, value.funder_id)
            program = await db.get(FundingProgram, value.program_id)
            application = await db.get(FundingApplication, value.application_id)
            return self._offer(value, funder, program, application)

    async def get_exposure(self, tenant_id: str, msme_id: str | None = None) -> dict[str, Any]:
        async with session() as db:
            commitments = (await db.scalars(select(FundingCommitment).where(FundingCommitment.tenant_id == tenant_id))).all()
            reservations = {value.id: value for value in (await db.scalars(select(OfferReservation).where(OfferReservation.tenant_id == tenant_id))).all()}
            programs = (await db.scalars(select(FundingProgram).where(FundingProgram.tenant_id == tenant_id))).all()
        filtered = [value for value in commitments if not msme_id or reservations.get(value.reservation_id, None) and reservations[value.reservation_id].msme_id == msme_id]
        return {
            "msme_id": msme_id,
            "committed_exposure": str(sum((value.committed_amount for value in filtered if value.status in {"COMMITTED", "DISBURSED", "SETTLED"}), Decimal("0"))),
            "prepared_exposure": str(sum((value.committed_amount for value in filtered if value.status == "PREPARED"), Decimal("0"))),
            "programs": [{"program_id": value.id, "available_capacity": str(self._available(value)), "reserved_capacity": str(value.reserved_capacity), "committed_capacity": str(value.committed_capacity)} for value in programs],
            "retrieved_at": datetime.now(UTC).isoformat(),
        }

    async def consume_external_event(
        self, event: ExternalEventEnvelope, signed_payload_hash: str
    ) -> dict[str, Any]:
        async with session() as db:
            existing = await db.scalar(select(InboxEvent).where(InboxEvent.source_application == event.source_application, InboxEvent.event_id == event.event_id))
            if existing:
                return {"status": "DUPLICATE_IGNORED", "event_id": event.event_id}
            inbox = InboxEvent(
                id=str(uuid4()), source_application=event.source_application,
                event_id=event.event_id, event_type=event.event_type,
                tenant_id=event.tenant_id, status="RECEIVED", payload_hash=signed_payload_hash,
            )
            db.add(inbox)
            commitment_id = str(event.aggregate.get("id", ""))
            value = await self._commitment_model(db, event.tenant_id, commitment_id, lock=True)
            version = int(event.aggregate.get("version", 0))
            if version <= value.version:
                inbox.status = "PROCESSED"
                inbox.processed_at = datetime.now(UTC)
                return {"status": "STALE_VERSION_IGNORED", "event_id": event.event_id}
            if event.event_type == "commitment.disbursed":
                value.status = "DISBURSED"
                value.ledger_reference = str(event.data.get("ledger_reference", "")) or None
            elif event.event_type == "commitment.settled":
                value.status = "SETTLED"
                value.settlement_status = "SETTLED"
            else:
                value.status = "EXECUTION_REVIEW_REQUIRED"
                value.settlement_status = "UNKNOWN"
            value.version = version
            self._record(db, value, event.event_type, event.source_application, event.correlation_id, event.data, actor_type="SERVICE")
            inbox.status = "PROCESSED"
            inbox.processed_at = datetime.now(UTC)
            return {"status": "PROCESSED", "event_id": event.event_id, "commitment_id": value.id}

    def evidence_receipt(self, call_id: str, kind: str, tenant_id: str, refs: list[str]) -> str:
        canonical = json.dumps({"call_id": call_id, "kind": kind, "tenant_id": tenant_id, "refs": sorted(refs)}, sort_keys=True, separators=(",", ":"))
        digest = hmac.new(get_settings().mcp_token.get_secret_value().encode(), canonical.encode(), hashlib.sha256).hexdigest()
        return f"evr_funder_demo_{digest[:32]}"

    @staticmethod
    def _available(value: FundingProgram) -> Decimal:
        return max(Decimal("0"), value.total_capacity - value.reserved_capacity - value.committed_capacity)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    def _eligibility_reasons(self, value: FundingProgram, amount: Decimal, tenor: int, region: str, industry: str) -> list[str]:
        reasons = []
        if amount < value.minimum_amount or amount > value.maximum_amount:
            reasons.append("AMOUNT_OUTSIDE_PROGRAM")
        if amount > self._available(value):
            reasons.append("PROGRAM_CAPACITY_UNAVAILABLE")
        if tenor < value.tenor_minimum_days or tenor > value.tenor_maximum_days:
            reasons.append("TENOR_OUTSIDE_PROGRAM")
        if region not in value.eligible_regions:
            reasons.append("REGION_NOT_ELIGIBLE")
        if industry not in value.eligible_industries:
            reasons.append("INDUSTRY_NOT_ELIGIBLE")
        return reasons

    @staticmethod
    def _expect_version(current: int, expected: int) -> None:
        if current != expected:
            raise FunderConflictError(f"Version conflict: current version is {current}.")

    async def _application_model(self, db: AsyncSession, tenant_id: str, value_id: str, lock: bool = False) -> FundingApplication:
        query = select(FundingApplication).where(FundingApplication.tenant_id == tenant_id, FundingApplication.id == value_id)
        value = await db.scalar(query.with_for_update() if lock else query)
        if value is None:
            raise FunderNotFoundError("Funding application was not found in the signed tenant scope.")
        return value

    async def _program_model(self, db: AsyncSession, tenant_id: str, value_id: str, lock: bool = False) -> FundingProgram:
        query = select(FundingProgram).where(FundingProgram.tenant_id == tenant_id, FundingProgram.id == value_id)
        value = await db.scalar(query.with_for_update() if lock else query)
        if value is None:
            raise FunderNotFoundError("Funding program was not found in the signed tenant scope.")
        return value

    async def _offer_model(self, db: AsyncSession, tenant_id: str, value_id: str, lock: bool = False) -> FundingOffer:
        query = select(FundingOffer).where(FundingOffer.tenant_id == tenant_id, FundingOffer.id == value_id)
        value = await db.scalar(query.with_for_update() if lock else query)
        if value is None:
            raise FunderNotFoundError("Funding offer was not found in the signed tenant scope.")
        return value

    async def _reservation_model(self, db: AsyncSession, tenant_id: str, value_id: str, lock: bool = False) -> OfferReservation:
        query = select(OfferReservation).where(OfferReservation.tenant_id == tenant_id, OfferReservation.id == value_id)
        value = await db.scalar(query.with_for_update() if lock else query)
        if value is None:
            raise FunderNotFoundError("Offer reservation was not found in the signed tenant scope.")
        return value

    async def _commitment_model(self, db: AsyncSession, tenant_id: str, value_id: str, lock: bool = False) -> FundingCommitment:
        query = select(FundingCommitment).where(FundingCommitment.tenant_id == tenant_id, FundingCommitment.id == value_id)
        value = await db.scalar(query.with_for_update() if lock else query)
        if value is None:
            raise FunderNotFoundError("Funding commitment was not found in the signed tenant scope.")
        return value

    def _record(self, db: AsyncSession, aggregate: Any, event_type: str, actor: str, correlation_id: str, payload: dict[str, Any], actor_type: str = "USER") -> None:
        aggregate_type = type(aggregate).__name__
        db.add(AuditEvent(
            id=str(uuid4()), tenant_id=aggregate.tenant_id, aggregate_type=aggregate_type,
            aggregate_id=aggregate.id, aggregate_version=aggregate.version,
            event_type=event_type, actor_type=actor_type, actor_id=actor,
            reason=str(payload.get("reason")) if payload.get("reason") else None,
            payload=payload, correlation_id=correlation_id,
        ))
        db.add(OutboxEvent(
            id=str(uuid4()), tenant_id=aggregate.tenant_id, aggregate_type=aggregate_type,
            aggregate_id=aggregate.id, aggregate_version=aggregate.version,
            event_type=event_type, payload=payload, correlation_id=correlation_id,
        ))

    @staticmethod
    def _commitment_action(reservation_id: str, amount: Decimal, destination_token: str) -> dict[str, str]:
        return {"reservation_id": reservation_id, "amount": str(amount), "destination_token": destination_token}

    @staticmethod
    def _hash(value: Any) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

    @staticmethod
    def _funder(value: FunderInstitution) -> dict[str, Any]:
        return {"id": value.id, "legal_name": value.legal_name, "display_name": value.display_name, "institution_type": value.institution_type, "status": value.status, "supported_currencies": value.supported_currencies, "supported_rails": value.supported_rails, "policy_metadata": value.policy_metadata, "version": value.version}

    def _program(self, value: FundingProgram, funder: FunderInstitution | None, rules: list[ProgramRule]) -> dict[str, Any]:
        return {"id": value.id, "funder_id": value.funder_id, "funder_name": funder.display_name if funder else None, "program_code": value.program_code, "name": value.name, "product_type": value.product_type, "currency": value.currency, "minimum_amount": str(value.minimum_amount), "maximum_amount": str(value.maximum_amount), "total_capacity": str(value.total_capacity), "reserved_capacity": str(value.reserved_capacity), "committed_capacity": str(value.committed_capacity), "available_capacity": str(self._available(value)), "advance_rate_maximum": str(value.advance_rate_maximum), "tenor_minimum_days": value.tenor_minimum_days, "tenor_maximum_days": value.tenor_maximum_days, "pricing_model": value.pricing_model, "eligible_regions": value.eligible_regions, "eligible_industries": value.eligible_industries, "required_evidence_types": value.required_evidence_types, "status": value.status, "policy_version": value.policy_version, "version": value.version, "rules": [{"id": rule.id, "rule_key": rule.rule_key, "input_field": rule.input_field, "operator": rule.operator, "comparison_value": rule.comparison_value, "reason_code": rule.reason_code, "version": rule.version} for rule in rules]}

    @staticmethod
    def _application(value: FundingApplication) -> dict[str, Any]:
        return {"id": value.id, "case_id": value.case_id, "msme_id": value.msme_id, "msme_name": value.msme_name, "receivable_id": value.receivable_id, "requested_amount": str(value.requested_amount), "currency": value.currency, "tenor_days": value.tenor_days, "region": value.region, "industry": value.industry, "evidence_receipt_ids": value.evidence_receipt_ids, "exposure_snapshot_reference": value.exposure_snapshot_reference, "exposure_amount": str(value.exposure_amount), "eligibility_results": value.eligibility_results, "status": value.status, "submitted_at": value.submitted_at.isoformat(), "reviewed_by": value.reviewed_by, "version": value.version}

    @staticmethod
    def _offer(value: FundingOffer, funder: FunderInstitution | None, program: FundingProgram | None, application: FundingApplication | None) -> dict[str, Any]:
        return {"id": value.id, "application_id": value.application_id, "case_id": application.case_id if application else None, "msme_name": application.msme_name if application else None, "funder_id": value.funder_id, "funder_name": funder.display_name if funder else None, "program_id": value.program_id, "program_name": program.name if program else None, "approved_amount": str(value.approved_amount), "advance_rate": str(value.advance_rate), "annual_rate": str(value.annual_rate), "fee_amount": str(value.fee_amount), "tenor_days": value.tenor_days, "repayment_terms": value.repayment_terms, "conditions": value.conditions, "expires_at": value.expires_at.isoformat(), "status": value.status, "offer_hash": value.offer_hash, "version": value.version}

    @staticmethod
    def _reservation(value: OfferReservation) -> dict[str, Any]:
        return {"id": value.id, "offer_id": value.offer_id, "program_id": value.program_id, "reserved_amount": str(value.reserved_amount), "case_id": value.case_id, "msme_id": value.msme_id, "expires_at": value.expires_at.isoformat(), "status": value.status, "release_reference": value.release_reference, "commit_reference": value.commit_reference, "version": value.version}

    @staticmethod
    def _commitment(value: FundingCommitment, reservation: OfferReservation | None) -> dict[str, Any]:
        return {"id": value.id, "reservation_id": value.reservation_id, "case_id": reservation.case_id if reservation else None, "msme_id": reservation.msme_id if reservation else None, "committed_amount": str(value.committed_amount), "guardian_authorization_id": value.guardian_authorization_id, "action_hash": value.action_hash, "destination_token": value.destination_token, "status": value.status, "execution_reference": value.execution_reference, "ledger_reference": value.ledger_reference, "settlement_status": value.settlement_status, "version": value.version}

    @staticmethod
    def _audit(value: AuditEvent) -> dict[str, Any]:
        return {"id": value.id, "aggregate_type": value.aggregate_type, "aggregate_id": value.aggregate_id, "aggregate_version": value.aggregate_version, "event_type": value.event_type, "actor_type": value.actor_type, "actor_id": value.actor_id, "reason": value.reason, "payload": value.payload, "correlation_id": value.correlation_id, "occurred_at": value.occurred_at.isoformat()}


funder_service = FunderService()
