import hashlib
import hmac
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select

from .database import session
from .domain import canonical_hash, iso
from .mcp_security import RuntimeScope
from .models import ClassificationSnapshot, Enterprise, Invoice, ReturnSummary, Taxpayer
from .service import GstNotFoundError, gst_service
from .settings import get_settings


class GstMcpService:
    async def classification(self, scope: RuntimeScope) -> dict[str, Any]:
        async with session() as db:
            enterprise = await self._enterprise(db, scope)
            snapshot = await db.scalar(
                select(ClassificationSnapshot)
                .where(
                    ClassificationSnapshot.tenant_id == scope.tenant_id,
                    ClassificationSnapshot.enterprise_id == enterprise.id,
                )
                .order_by(ClassificationSnapshot.created_at.desc())
                .limit(1)
            )
            if snapshot is None:
                raise GstNotFoundError("Classification snapshot was not found.")
            return self._wrap(
                scope,
                "gst.classification.v1",
                gst_service.classification_projection(snapshot),
                enterprise.version,
                enterprise.updated_at,
            )

    async def taxpayer(self, scope: RuntimeScope, gstin: str) -> dict[str, Any]:
        async with session() as db:
            enterprise = await self._enterprise(db, scope)
            value = await db.scalar(
                select(Taxpayer).where(
                    Taxpayer.tenant_id == scope.tenant_id,
                    Taxpayer.enterprise_id == enterprise.id,
                    Taxpayer.gstin == gstin.upper(),
                )
            )
            if value is None:
                raise GstNotFoundError("Taxpayer was not found in the signed enterprise scope.")
            return self._wrap(
                scope,
                "gst.taxpayer.v1",
                gst_service.taxpayer_projection(value),
                value.version,
                value.updated_at,
            )

    async def registration(self, scope: RuntimeScope, gstin: str) -> dict[str, Any]:
        result = await self.taxpayer(scope, gstin)
        taxpayer = result["data"]
        result["data"] = {
            "gstin": taxpayer["gstin"],
            "registration_status": taxpayer["registration_status"],
            "registration_date": taxpayer["registration_date"],
            "active_match": taxpayer["registration_status"] == "ACTIVE",
            "risk_flags": taxpayer["risk_flags"],
        }
        result["schema_version"] = "gst.registration.v1"
        return result

    async def invoice_get(
        self,
        scope: RuntimeScope,
        *,
        invoice_id: str | None,
        seller_gstin: str | None,
        invoice_number: str | None,
        financial_year: str | None,
    ) -> dict[str, Any]:
        async with session() as db:
            enterprise = await self._enterprise(db, scope)
            statement = select(Invoice).where(
                Invoice.tenant_id == scope.tenant_id,
                Invoice.enterprise_id == enterprise.id,
            )
            if invoice_id:
                statement = statement.where(Invoice.id == invoice_id)
            elif seller_gstin and invoice_number and financial_year:
                statement = statement.where(
                    Invoice.seller_gstin == seller_gstin.upper(),
                    Invoice.invoice_number == invoice_number.upper(),
                    Invoice.financial_year == financial_year,
                )
            else:
                raise ValueError(
                    "Provide invoice_id or seller_gstin, invoice_number and financial_year."
                )
            value = await db.scalar(statement.limit(1))
            if value is None:
                raise GstNotFoundError("Invoice was not found in the signed enterprise scope.")
            return self._wrap(
                scope,
                "gst.invoice.v1",
                gst_service.invoice_projection(value, []),
                value.version,
                value.updated_at,
            )

    async def invoice_search(
        self,
        scope: RuntimeScope,
        *,
        query: str | None,
        status: str | None,
        limit: int,
    ) -> dict[str, Any]:
        async with session() as db:
            enterprise = await self._enterprise(db, scope)
            statement = select(Invoice).where(
                Invoice.tenant_id == scope.tenant_id,
                Invoice.enterprise_id == enterprise.id,
            )
            if status:
                statement = statement.where(Invoice.status == status.upper())
            if query:
                term = f"%{query.strip()}%"
                statement = statement.where(
                    or_(
                        Invoice.invoice_number.ilike(term),
                        Invoice.buyer_name.ilike(term),
                        Invoice.buyer_gstin.ilike(term),
                    )
                )
            values = (
                await db.scalars(
                    statement.order_by(Invoice.invoice_date.desc()).limit(max(1, min(limit, 100)))
                )
            ).all()
            updated = max((value.updated_at for value in values), default=datetime.now(UTC))
            version = max((value.version for value in values), default=1)
            return self._wrap(
                scope,
                "gst.invoice-search.v1",
                {"items": [gst_service.invoice_summary(value) for value in values]},
                version,
                updated,
            )

    async def invoice_verify(
        self,
        scope: RuntimeScope,
        *,
        invoice_id: str,
        claimed_total: str | None,
        claimed_buyer_gstin: str | None,
        claimed_status: str | None,
    ) -> dict[str, Any]:
        source = await self.invoice_get(
            scope,
            invoice_id=invoice_id,
            seller_gstin=None,
            invoice_number=None,
            financial_year=None,
        )
        invoice = source["data"]
        comparisons: dict[str, dict[str, Any]] = {}
        if claimed_total is not None:
            comparisons["total_invoice_value"] = {
                "claimed": str(Decimal(claimed_total).quantize(Decimal("0.01"))),
                "source": invoice["total_invoice_value"],
                "match": Decimal(claimed_total).quantize(Decimal("0.01"))
                == Decimal(invoice["total_invoice_value"]),
            }
        if claimed_buyer_gstin is not None:
            comparisons["buyer_gstin"] = {
                "claimed": claimed_buyer_gstin.upper(),
                "source": invoice["buyer_gstin"],
                "match": claimed_buyer_gstin.upper() == invoice["buyer_gstin"],
            }
        if claimed_status is not None:
            comparisons["status"] = {
                "claimed": claimed_status.upper(),
                "source": invoice["status"],
                "match": claimed_status.upper() == invoice["status"],
            }
        source["schema_version"] = "gst.invoice-verification.v1"
        source["data"] = {
            "invoice_id": invoice_id,
            "verified": bool(comparisons) and all(item["match"] for item in comparisons.values()),
            "eligible_registered_invoice": invoice["status"] == "REGISTERED",
            "comparisons": comparisons,
            "source_record": invoice,
        }
        return source

    async def duplicate_check(
        self,
        scope: RuntimeScope,
        *,
        seller_gstin: str,
        invoice_number: str,
        invoice_date: date,
        total_invoice_value: str,
    ) -> dict[str, Any]:
        async with session() as db:
            enterprise = await self._enterprise(db, scope)
            candidates = (
                await db.scalars(
                    select(Invoice).where(
                        Invoice.tenant_id == scope.tenant_id,
                        Invoice.enterprise_id == enterprise.id,
                        Invoice.seller_gstin == seller_gstin.upper(),
                        or_(
                            Invoice.invoice_number == invoice_number.upper(),
                            (Invoice.invoice_date == invoice_date)
                            & (
                                Invoice.total_invoice_value
                                == Decimal(total_invoice_value).quantize(Decimal("0.01"))
                            ),
                        ),
                    )
                )
            ).all()
            return self._wrap(
                scope,
                "gst.invoice-duplicate.v1",
                {
                    "duplicate_found": bool(candidates),
                    "candidates": [gst_service.invoice_summary(value) for value in candidates],
                    "reason_codes": ["SELLER_NUMBER_OR_DATE_VALUE_MATCH"] if candidates else [],
                },
                max((value.version for value in candidates), default=1),
                max((value.updated_at for value in candidates), default=datetime.now(UTC)),
            )

    async def return_summary(
        self, scope: RuntimeScope, period: str, return_type: str
    ) -> dict[str, Any]:
        async with session() as db:
            enterprise = await self._enterprise(db, scope)
            value = await db.scalar(
                select(ReturnSummary)
                .where(
                    ReturnSummary.tenant_id == scope.tenant_id,
                    ReturnSummary.enterprise_id == enterprise.id,
                    ReturnSummary.period == period,
                    ReturnSummary.return_type == return_type,
                )
                .order_by(ReturnSummary.version.desc())
                .limit(1)
            )
            if value is None:
                raise GstNotFoundError("Return summary was not found in the signed scope.")
            return self._wrap(
                scope,
                "gst.return-summary.v1",
                gst_service.return_projection(value),
                value.version,
                value.updated_at,
            )

    @staticmethod
    async def _enterprise(db: Any, scope: RuntimeScope) -> Enterprise:
        enterprise = await db.scalar(
            select(Enterprise).where(
                Enterprise.id == scope.organization_id,
                Enterprise.tenant_id == scope.tenant_id,
                Enterprise.status == "ACTIVE",
            )
        )
        if enterprise is None:
            raise GstNotFoundError("Enterprise was not found in the signed runtime scope.")
        return enterprise

    @staticmethod
    def _wrap(
        scope: RuntimeScope,
        schema_version: str,
        data: dict[str, Any],
        record_version: int,
        updated_at: datetime,
    ) -> dict[str, Any]:
        retrieved = datetime.now(UTC)
        body = {
            "schema_version": schema_version,
            "source_system": "xyena-demo-gst",
            "request_id": scope.call_id,
            "record_version": record_version,
            "updated_at": iso(updated_at),
            "retrieved_at": retrieved.isoformat(),
            "fresh_until": (retrieved + timedelta(minutes=5)).isoformat(),
            "data": data,
            "security_labels": ["EXTERNAL_DATA", "SYNTHETIC_DEMO_SOURCE"],
        }
        signature = hmac.new(
            get_settings().mcp_token.get_secret_value().encode(),
            json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode(),
            hashlib.sha256,
        ).hexdigest()
        body["source_signature"] = signature
        body["source_hash"] = canonical_hash(data)
        return body


gst_mcp_service = GstMcpService()
