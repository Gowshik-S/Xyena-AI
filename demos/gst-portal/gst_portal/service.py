import secrets
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import BrowserScope, require_roles
from .domain import (
    THRESHOLD_VERSION,
    calculate_line,
    canonical_hash,
    classify_msme,
    financial_year,
    iso,
    money,
    record_change,
)
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
)
from .schemas import ClassificationReviewRequest, InvoiceCreate


class GstDomainError(RuntimeError):
    pass


class GstNotFoundError(GstDomainError):
    pass


class GstConflictError(GstDomainError):
    pass


class GstPortalService:
    async def session_view(self, db: AsyncSession, scope: BrowserScope) -> dict[str, Any]:
        memberships = (
            await db.execute(
                select(EnterpriseMembership, Enterprise)
                .join(Enterprise, Enterprise.id == EnterpriseMembership.enterprise_id)
                .where(
                    EnterpriseMembership.user_id == scope.user.id,
                    EnterpriseMembership.status == "ACTIVE",
                )
                .order_by(Enterprise.trade_name)
            )
        ).all()
        return {
            "user": {
                "id": scope.user.id,
                "display_name": scope.user.display_name,
                "email": scope.user.email,
            },
            "enterprise": self.enterprise_projection(scope.enterprise),
            "roles": sorted(scope.roles),
            "memberships": [
                {
                    "enterprise_id": enterprise.id,
                    "trade_name": enterprise.trade_name,
                    "gstin": enterprise.primary_gstin,
                    "classification": enterprise.effective_classification,
                }
                for _, enterprise in memberships
            ],
            "environment": "SYNTHETIC_NON_PRODUCTION",
        }

    async def dashboard(self, db: AsyncSession, scope: BrowserScope) -> dict[str, Any]:
        status_rows = (
            await db.execute(
                select(Invoice.status, func.count(Invoice.id))
                .where(
                    Invoice.tenant_id == scope.enterprise.tenant_id,
                    Invoice.enterprise_id == scope.enterprise.id,
                )
                .group_by(Invoice.status)
            )
        ).all()
        totals = (
            await db.execute(
                select(
                    func.coalesce(func.sum(Invoice.taxable_value), 0),
                    func.coalesce(
                        func.sum(
                            Invoice.cgst_amount + Invoice.sgst_amount + Invoice.igst_amount
                        ),
                        0,
                    ),
                ).where(
                    Invoice.tenant_id == scope.enterprise.tenant_id,
                    Invoice.enterprise_id == scope.enterprise.id,
                    Invoice.status == "REGISTERED",
                )
            )
        ).one()
        recent = (
            await db.scalars(
                select(Invoice)
                .where(
                    Invoice.tenant_id == scope.enterprise.tenant_id,
                    Invoice.enterprise_id == scope.enterprise.id,
                )
                .order_by(Invoice.updated_at.desc())
                .limit(6)
            )
        ).all()
        snapshot = await self._latest_snapshot(db, scope.enterprise)
        return {
            "enterprise": self.enterprise_projection(scope.enterprise),
            "invoice_counts": {status: count for status, count in status_rows},
            "registered_taxable_turnover": str(totals[0]),
            "registered_tax_total": str(totals[1]),
            "recent_invoices": [self.invoice_summary(value) for value in recent],
            "classification": self.classification_projection(snapshot),
            "environment": "SYNTHETIC_NON_PRODUCTION",
        }

    async def list_invoices(
        self,
        db: AsyncSession,
        scope: BrowserScope,
        *,
        query: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        statement = select(Invoice).where(
            Invoice.tenant_id == scope.enterprise.tenant_id,
            Invoice.enterprise_id == scope.enterprise.id,
        )
        if status:
            statement = statement.where(Invoice.status == status)
        if query:
            term = f"%{query.strip()}%"
            statement = statement.where(
                or_(
                    Invoice.invoice_number.ilike(term),
                    Invoice.buyer_name.ilike(term),
                    Invoice.buyer_gstin.ilike(term),
                    Invoice.irn.ilike(term),
                )
            )
        values = (
            await db.scalars(statement.order_by(Invoice.invoice_date.desc()).limit(min(limit, 100)))
        ).all()
        return [self.invoice_summary(value) for value in values]

    async def get_invoice(
        self, db: AsyncSession, scope: BrowserScope, invoice_id: str
    ) -> dict[str, Any]:
        invoice = await self._invoice(db, scope.enterprise, invoice_id)
        history = (
            await db.scalars(
                select(InvoiceStatusHistory)
                .where(InvoiceStatusHistory.invoice_id == invoice.id)
                .order_by(InvoiceStatusHistory.occurred_at)
            )
        ).all()
        return self.invoice_projection(invoice, history)

    async def create_invoice(
        self, db: AsyncSession, scope: BrowserScope, request: InvoiceCreate
    ) -> dict[str, Any]:
        require_roles(scope, "GST_OPERATOR")
        if request.invoice_date > date.today():
            raise GstDomainError("Invoice date cannot be in the future.")
        fy = financial_year(request.invoice_date)
        exists = await db.scalar(
            select(Invoice.id).where(
                Invoice.enterprise_id == scope.enterprise.id,
                Invoice.financial_year == fy,
                Invoice.invoice_number == request.invoice_number,
            )
        )
        if exists:
            raise GstConflictError("This invoice number already exists for the financial year.")
        intra_state = scope.enterprise.primary_gstin[:2] == request.place_of_supply
        line_values: list[tuple[Any, dict[str, Decimal]]] = []
        for line in request.lines:
            try:
                amounts = calculate_line(
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    discount=line.discount,
                    gst_rate=line.gst_rate,
                    intra_state=intra_state,
                )
            except ValueError as exc:
                raise GstDomainError(str(exc)) from exc
            line_values.append((line, amounts))
        taxable = money(sum((value[1]["taxable_value"] for value in line_values), Decimal("0")))
        cgst = money(sum((value[1]["cgst_amount"] for value in line_values), Decimal("0")))
        sgst = money(sum((value[1]["sgst_amount"] for value in line_values), Decimal("0")))
        igst = money(sum((value[1]["igst_amount"] for value in line_values), Decimal("0")))
        invoice = Invoice(
            id=str(uuid4()),
            tenant_id=scope.enterprise.tenant_id,
            enterprise_id=scope.enterprise.id,
            invoice_number=request.invoice_number,
            invoice_type=request.invoice_type,
            invoice_date=request.invoice_date,
            financial_year=fy,
            seller_gstin=scope.enterprise.primary_gstin,
            buyer_gstin=request.buyer_gstin,
            buyer_name=request.buyer_name,
            purchase_order_id=request.purchase_order_id,
            currency="INR",
            place_of_supply=request.place_of_supply,
            taxable_value=taxable,
            cgst_amount=cgst,
            sgst_amount=sgst,
            igst_amount=igst,
            cess_amount=Decimal("0.00"),
            total_invoice_value=money(taxable + cgst + sgst + igst),
            status="DRAFT",
            security_flags=[],
            version=1,
            created_by=scope.user.id,
            updated_by=scope.user.id,
        )
        db.add(invoice)
        await db.flush()
        for index, (line, amounts) in enumerate(line_values, start=1):
            db.add(
                InvoiceLine(
                    id=str(uuid4()),
                    invoice_id=invoice.id,
                    line_number=index,
                    description=line.description,
                    hsn_sac=line.hsn_sac,
                    quantity=line.quantity,
                    unit=line.unit,
                    unit_price=line.unit_price,
                    discount=line.discount,
                    taxable_value=amounts["taxable_value"],
                    gst_rate=line.gst_rate,
                    cgst_amount=amounts["cgst_amount"],
                    sgst_amount=amounts["sgst_amount"],
                    igst_amount=amounts["igst_amount"],
                    total_value=amounts["total_value"],
                )
            )
        self._history(db, invoice, None, "DRAFT", scope.user.id, "Invoice created")
        record_change(
            db,
            tenant_id=invoice.tenant_id,
            aggregate_type="INVOICE",
            aggregate_id=invoice.id,
            aggregate_version=invoice.version,
            event_type="invoice.created",
            actor_type="USER",
            actor_id=scope.user.id,
        )
        await db.flush()
        await db.refresh(invoice, attribute_names=["lines"])
        return self.invoice_projection(invoice, [])

    async def transition_invoice(
        self,
        db: AsyncSession,
        scope: BrowserScope,
        invoice_id: str,
        action: str,
        *,
        expected_version: int,
        reason: str | None,
    ) -> dict[str, Any]:
        invoice = await self._invoice(db, scope.enterprise, invoice_id, lock=True)
        if invoice.version != expected_version:
            raise GstConflictError("The invoice changed. Reload it before applying this action.")
        transitions = {
            "submit": ("DRAFT", "SUBMITTED", ("GST_OPERATOR",)),
            "register": ("SUBMITTED", "REGISTERED", ("GST_REVIEWER",)),
            "reject": ("SUBMITTED", "REJECTED", ("GST_REVIEWER",)),
            "cancel": ("REGISTERED", "CANCELLED", ("GST_REVIEWER",)),
        }
        if action not in transitions:
            raise GstDomainError("Unsupported invoice transition.")
        expected, target, roles = transitions[action]
        require_roles(scope, *roles)
        if invoice.status != expected:
            raise GstConflictError(f"Only a {expected} invoice can be {action}ed.")
        if action in {"reject", "cancel"} and not (reason or "").strip():
            raise GstDomainError("A reason is required for rejection or cancellation.")
        prior = invoice.status
        invoice.status = target
        invoice.version += 1
        invoice.updated_by = scope.user.id
        if action == "submit":
            invoice.source_document_hash = canonical_hash(self.invoice_projection(invoice, []))
        elif action == "register":
            invoice.irn = f"IRNDEMO{canonical_hash({'id': invoice.id, 'v': invoice.version})[:24].upper()}"
            invoice.ack_number = f"ACK{datetime.now(UTC):%y%m%d}{secrets.randbelow(10**6):06d}"
            invoice.ack_date = datetime.now(UTC)
        elif action == "cancel":
            invoice.cancellation_reason = reason
        self._history(db, invoice, prior, target, scope.user.id, reason)
        record_change(
            db,
            tenant_id=invoice.tenant_id,
            aggregate_type="INVOICE",
            aggregate_id=invoice.id,
            aggregate_version=invoice.version,
            event_type=f"invoice.{target.lower()}",
            actor_type="USER",
            actor_id=scope.user.id,
            reason=reason,
        )
        return self.invoice_projection(invoice, [])

    async def taxpayers(self, db: AsyncSession, scope: BrowserScope) -> list[dict[str, Any]]:
        values = (
            await db.scalars(
                select(Taxpayer)
                .where(
                    Taxpayer.tenant_id == scope.enterprise.tenant_id,
                    Taxpayer.enterprise_id == scope.enterprise.id,
                )
                .order_by(Taxpayer.trade_name)
            )
        ).all()
        return [self.taxpayer_projection(value) for value in values]

    async def classification(self, db: AsyncSession, scope: BrowserScope) -> dict[str, Any]:
        return self.classification_projection(await self._latest_snapshot(db, scope.enterprise))

    async def recalculate_classification(
        self, db: AsyncSession, scope: BrowserScope
    ) -> dict[str, Any]:
        require_roles(scope, "GST_REVIEWER")
        current = await self._latest_snapshot(db, scope.enterprise)
        calculated = classify_msme(current.investment_amount, current.annual_turnover)
        verification = (
            "VERIFIED" if calculated == current.declared_classification else "REVIEW_REQUIRED"
        )
        snapshot = ClassificationSnapshot(
            id=str(uuid4()),
            tenant_id=current.tenant_id,
            enterprise_id=current.enterprise_id,
            financial_year=current.financial_year,
            investment_amount=current.investment_amount,
            annual_turnover=current.annual_turnover,
            declared_classification=current.declared_classification,
            calculated_classification=calculated,
            effective_classification=current.effective_classification,
            source_type="DEMO_DERIVED",
            source_reference=f"recalc_{uuid4().hex[:12]}",
            source_hash=canonical_hash(
                {"investment": current.investment_amount, "turnover": current.annual_turnover}
            ),
            threshold_policy_version=THRESHOLD_VERSION,
            verification_status=verification,
            effective_from=date.today(),
            created_at=datetime.now(UTC),
        )
        db.add(snapshot)
        scope.enterprise.calculated_classification = calculated
        scope.enterprise.classification_provenance = (
            "DEMO_DERIVED" if verification == "VERIFIED" else "REVIEW_REQUIRED"
        )
        scope.enterprise.classification_as_of = date.today()
        scope.enterprise.version += 1
        record_change(
            db,
            tenant_id=current.tenant_id,
            aggregate_type="ENTERPRISE",
            aggregate_id=current.enterprise_id,
            aggregate_version=scope.enterprise.version,
            event_type="enterprise.classification_recalculated",
            actor_type="USER",
            actor_id=scope.user.id,
        )
        return self.classification_projection(snapshot)

    async def review_classification(
        self,
        db: AsyncSession,
        scope: BrowserScope,
        request: ClassificationReviewRequest,
    ) -> dict[str, Any]:
        require_roles(scope, "GST_REVIEWER")
        current = await self._latest_snapshot(db, scope.enterprise)
        snapshot = ClassificationSnapshot(
            id=str(uuid4()),
            tenant_id=current.tenant_id,
            enterprise_id=current.enterprise_id,
            financial_year=current.financial_year,
            investment_amount=current.investment_amount,
            annual_turnover=current.annual_turnover,
            declared_classification=current.declared_classification,
            calculated_classification=current.calculated_classification,
            effective_classification=request.effective_classification,
            source_type="UDYAM_TEST_FIXTURE",
            source_reference=f"review_{uuid4().hex[:12]}",
            source_hash=canonical_hash(
                {
                    "prior_snapshot": current.id,
                    "effective_classification": request.effective_classification,
                    "reason": request.reason,
                }
            ),
            threshold_policy_version=current.threshold_policy_version,
            verification_status="VERIFIED",
            effective_from=date.today(),
            created_at=datetime.now(UTC),
        )
        db.add(snapshot)
        scope.enterprise.effective_classification = request.effective_classification
        scope.enterprise.classification_provenance = "UDYAM_TEST_FIXTURE"
        scope.enterprise.classification_as_of = date.today()
        scope.enterprise.version += 1
        record_change(
            db,
            tenant_id=current.tenant_id,
            aggregate_type="ENTERPRISE",
            aggregate_id=current.enterprise_id,
            aggregate_version=scope.enterprise.version,
            event_type="enterprise.classification_changed",
            actor_type="USER",
            actor_id=scope.user.id,
            reason=request.reason,
        )
        return self.classification_projection(snapshot)

    async def returns(self, db: AsyncSession, scope: BrowserScope) -> list[dict[str, Any]]:
        values = (
            await db.scalars(
                select(ReturnSummary)
                .where(
                    ReturnSummary.tenant_id == scope.enterprise.tenant_id,
                    ReturnSummary.enterprise_id == scope.enterprise.id,
                )
                .order_by(ReturnSummary.period.desc(), ReturnSummary.version.desc())
            )
        ).all()
        return [self.return_projection(value) for value in values]

    async def audit(self, db: AsyncSession, scope: BrowserScope) -> list[dict[str, Any]]:
        values = (
            await db.scalars(
                select(AuditEvent)
                .where(AuditEvent.tenant_id == scope.enterprise.tenant_id)
                .order_by(AuditEvent.occurred_at.desc())
                .limit(100)
            )
        ).all()
        return [
            {
                "id": value.id,
                "event_type": value.event_type,
                "aggregate_type": value.aggregate_type,
                "aggregate_id": value.aggregate_id,
                "version": value.aggregate_version,
                "actor_type": value.actor_type,
                "actor_id": value.actor_id,
                "reason": value.reason,
                "occurred_at": iso(value.occurred_at),
            }
            for value in values
        ]

    @staticmethod
    def enterprise_projection(value: Enterprise) -> dict[str, Any]:
        return {
            "id": value.id,
            "tenant_id": value.tenant_id,
            "business_id": value.business_id,
            "legal_name": value.legal_name,
            "trade_name": value.trade_name,
            "gstin": value.primary_gstin,
            "classification": value.effective_classification,
            "classification_provenance": value.classification_provenance,
            "financial_year": financial_year(date.today()),
            "status": value.status,
            "version": value.version,
        }

    @staticmethod
    def taxpayer_projection(value: Taxpayer) -> dict[str, Any]:
        return {
            "id": value.id,
            "gstin": value.gstin,
            "legal_name": value.legal_name,
            "trade_name": value.trade_name,
            "taxpayer_type": value.taxpayer_type,
            "registration_status": value.registration_status,
            "registration_date": value.registration_date.isoformat(),
            "state_code": value.state_code,
            "registered_address": value.registered_address,
            "risk_flags": value.risk_flags,
            "version": value.version,
            "updated_at": iso(value.updated_at),
        }

    @staticmethod
    def classification_projection(value: ClassificationSnapshot) -> dict[str, Any]:
        return {
            "id": value.id,
            "financial_year": value.financial_year,
            "investment_amount": str(value.investment_amount),
            "annual_turnover": str(value.annual_turnover),
            "declared_classification": value.declared_classification,
            "calculated_classification": value.calculated_classification,
            "effective_classification": value.effective_classification,
            "source_type": value.source_type,
            "source_reference": value.source_reference,
            "threshold_policy_version": value.threshold_policy_version,
            "verification_status": value.verification_status,
            "effective_from": value.effective_from.isoformat(),
            "created_at": iso(value.created_at),
        }

    @staticmethod
    def invoice_summary(value: Invoice) -> dict[str, Any]:
        return {
            "id": value.id,
            "invoice_number": value.invoice_number,
            "invoice_date": value.invoice_date.isoformat(),
            "financial_year": value.financial_year,
            "buyer_name": value.buyer_name,
            "buyer_gstin": value.buyer_gstin,
            "total_invoice_value": str(value.total_invoice_value),
            "status": value.status,
            "irn": value.irn,
            "version": value.version,
            "updated_at": iso(value.updated_at),
            "security_flags": value.security_flags,
        }

    def invoice_projection(
        self, value: Invoice, history: list[InvoiceStatusHistory]
    ) -> dict[str, Any]:
        result = self.invoice_summary(value)
        result.update(
            {
                "invoice_type": value.invoice_type,
                "seller_gstin": value.seller_gstin,
                "purchase_order_id": value.purchase_order_id,
                "place_of_supply": value.place_of_supply,
                "currency": value.currency,
                "taxable_value": str(value.taxable_value),
                "cgst_amount": str(value.cgst_amount),
                "sgst_amount": str(value.sgst_amount),
                "igst_amount": str(value.igst_amount),
                "cess_amount": str(value.cess_amount),
                "ack_number": value.ack_number,
                "ack_date": iso(value.ack_date),
                "source_document_hash": value.source_document_hash,
                "cancellation_reason": value.cancellation_reason,
                "lines": [
                    {
                        "id": line.id,
                        "line_number": line.line_number,
                        "description": line.description,
                        "hsn_sac": line.hsn_sac,
                        "quantity": str(line.quantity),
                        "unit": line.unit,
                        "unit_price": str(line.unit_price),
                        "discount": str(line.discount),
                        "taxable_value": str(line.taxable_value),
                        "gst_rate": str(line.gst_rate),
                        "cgst_amount": str(line.cgst_amount),
                        "sgst_amount": str(line.sgst_amount),
                        "igst_amount": str(line.igst_amount),
                        "total_value": str(line.total_value),
                    }
                    for line in value.lines
                ],
                "history": [
                    {
                        "prior_status": item.prior_status,
                        "new_status": item.new_status,
                        "reason": item.reason,
                        "actor_id": item.actor_id,
                        "version": item.version,
                        "occurred_at": iso(item.occurred_at),
                    }
                    for item in history
                ],
            }
        )
        return result

    @staticmethod
    def return_projection(value: ReturnSummary) -> dict[str, Any]:
        return {
            "id": value.id,
            "gstin": value.gstin,
            "period": value.period,
            "return_type": value.return_type,
            "version": value.version,
            "status": value.status,
            "turnover": str(value.turnover),
            "tax_total": str(value.tax_total),
            "invoice_count": value.invoice_count,
            "source_hash": value.source_hash,
            "updated_at": iso(value.updated_at),
        }

    @staticmethod
    async def _invoice(
        db: AsyncSession, enterprise: Enterprise, invoice_id: str, *, lock: bool = False
    ) -> Invoice:
        statement = select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == enterprise.tenant_id,
            Invoice.enterprise_id == enterprise.id,
        )
        if lock:
            statement = statement.with_for_update()
        invoice = await db.scalar(statement)
        if invoice is None:
            raise GstNotFoundError("Invoice was not found in the active enterprise scope.")
        return invoice

    @staticmethod
    async def _latest_snapshot(
        db: AsyncSession, enterprise: Enterprise
    ) -> ClassificationSnapshot:
        value = await db.scalar(
            select(ClassificationSnapshot)
            .where(
                ClassificationSnapshot.tenant_id == enterprise.tenant_id,
                ClassificationSnapshot.enterprise_id == enterprise.id,
            )
            .order_by(ClassificationSnapshot.created_at.desc())
            .limit(1)
        )
        if value is None:
            raise GstNotFoundError("Classification snapshot was not found.")
        return value

    @staticmethod
    def _history(
        db: AsyncSession,
        invoice: Invoice,
        prior: str | None,
        target: str,
        actor_id: str,
        reason: str | None,
    ) -> None:
        db.add(
            InvoiceStatusHistory(
                id=str(uuid4()),
                invoice_id=invoice.id,
                tenant_id=invoice.tenant_id,
                prior_status=prior,
                new_status=target,
                reason=reason,
                actor_id=actor_id,
                version=invoice.version,
            )
        )


gst_service = GstPortalService()
