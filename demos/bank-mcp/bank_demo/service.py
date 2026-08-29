import hashlib
import hmac
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select

from .database import session
from .events import demo_events
from .models import (
    Account,
    AuditEvent,
    Beneficiary,
    Consent,
    LedgerEntry,
    PreparedTransfer,
    Transaction,
    TransferExecution,
)
from .security import BankDemoSecurityError, RuntimeScope
from .settings import get_settings


class BankDemoDomainError(RuntimeError):
    pass


class BankDemoService:
    async def list_accounts(self, scope: RuntimeScope) -> dict[str, Any]:
        async with session() as db:
            await self._require_consent(db, scope)
            accounts = (
                await db.scalars(
                    select(Account).where(
                        Account.tenant_id == scope.tenant_id,
                        Account.user_id == scope.user_id,
                        Account.status == "ACTIVE",
                    )
                )
            ).all()
            result = {
                "status": "SUCCESS",
                "accounts": [self._account_projection(account) for account in accounts],
                "evidence_receipt_id": self._receipt(
                    scope, "accounts.list", [account.account_token for account in accounts]
                ),
                "security_flags": ["SYNTHETIC_DATA"],
            }
            self._audit(db, scope, "SUCCESS", {"account_count": len(accounts)})
            return result

    async def get_balance(self, scope: RuntimeScope, account_token: str) -> dict[str, Any]:
        async with session() as db:
            await self._require_consent(db, scope)
            account = await self._account(db, scope, account_token)
            result = {
                "status": "SUCCESS",
                "account_token": account.account_token,
                "currency": account.currency,
                "current_balance": str(account.current_balance),
                "available_balance": str(account.available_balance),
                "as_of": datetime.now(UTC).isoformat(),
                "evidence_receipt_id": self._receipt(
                    scope,
                    "accounts.get_balance",
                    [account.account_token, str(account.available_balance)],
                ),
                "security_flags": ["SYNTHETIC_DATA"],
            }
            self._audit(db, scope, "SUCCESS", {"account_token": account.account_token})
            return result

    async def list_transactions(
        self,
        scope: RuntimeScope,
        account_token: str,
        from_date: date,
        to_date: date,
        limit: int,
    ) -> dict[str, Any]:
        if from_date > to_date:
            raise BankDemoDomainError("from_date must not be after to_date.")
        if (to_date - from_date).days > 90:
            raise BankDemoDomainError("The synthetic demo limits transaction windows to 90 days.")
        limit = max(1, min(limit, 100))
        async with session() as db:
            await self._require_consent(db, scope)
            account = await self._account(db, scope, account_token)
            values = (
                await db.scalars(
                    select(Transaction)
                    .where(
                        Transaction.account_token == account.account_token,
                        Transaction.booked_on >= from_date,
                        Transaction.booked_on <= to_date,
                    )
                    .order_by(Transaction.booked_on.desc())
                    .limit(limit)
                )
            ).all()
            result = {
                "status": "SUCCESS",
                "account_token": account.account_token,
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
                "transactions": [
                    {
                        "transaction_id": value.id,
                        "booked_on": value.booked_on.isoformat(),
                        "direction": value.direction,
                        "amount": str(value.amount),
                        "currency": value.currency,
                        "category": value.category,
                        "description": value.description,
                        "reference": value.reference,
                    }
                    for value in values
                ],
                "evidence_receipt_id": self._receipt(
                    scope, "transactions.list", [value.id for value in values]
                ),
                "security_flags": ["SYNTHETIC_DATA"],
            }
            self._audit(db, scope, "SUCCESS", {"transaction_count": len(values)})
            return result

    async def verify_beneficiary(
        self, scope: RuntimeScope, beneficiary_token: str
    ) -> dict[str, Any]:
        async with session() as db:
            await self._require_consent(db, scope)
            value = await db.scalar(
                select(Beneficiary).where(
                    Beneficiary.beneficiary_token == beneficiary_token,
                    Beneficiary.tenant_id == scope.tenant_id,
                )
            )
            if value is None:
                raise BankDemoDomainError("Beneficiary was not found in the signed tenant scope.")
            result = {
                "status": "SUCCESS",
                "beneficiary_token": value.beneficiary_token,
                "owner_name": value.owner_name,
                "masked_account": value.masked_account,
                "bank_name": value.bank_name,
                "currency": value.currency,
                "verified": value.verified,
                "beneficiary_status": value.status,
                "evidence_receipt_id": self._receipt(
                    scope, "beneficiaries.verify", [value.beneficiary_token, value.status]
                ),
                "security_flags": ["SYNTHETIC_DATA"]
                + ([] if value.verified else ["BENEFICIARY_UNVERIFIED"]),
            }
            self._audit(db, scope, "SUCCESS", {"beneficiary_token": value.beneficiary_token})
            return result

    async def get_limits(self, scope: RuntimeScope, account_token: str) -> dict[str, Any]:
        async with session() as db:
            await self._require_consent(db, scope)
            account = await self._account(db, scope, account_token)
            result = {
                "status": "SUCCESS",
                "account_token": account.account_token,
                "currency": account.currency,
                "per_transfer": str(account.per_transfer_limit),
                "per_day": str(account.daily_limit),
                "allowed_rails": ["DEMO_BANK_RAIL"],
                "execution_available": True,
                "execution_mode": "SYNTHETIC_GUARDIAN_AUTHORIZED",
                "security_flags": ["SYNTHETIC_DATA", "GUARDIAN_AUTH_REQUIRED"],
            }
            self._audit(db, scope, "SUCCESS", {"account_token": account.account_token})
            return result

    async def prepare_transfer(
        self,
        scope: RuntimeScope,
        source_account_token: str,
        beneficiary_token: str,
        amount: str,
        currency: str,
        rail: str,
        client_idempotency_key: str,
    ) -> dict[str, Any]:
        try:
            decimal_amount = Decimal(amount).quantize(Decimal("0.01"))
        except InvalidOperation as exc:
            raise BankDemoDomainError("Amount must be a decimal value.") from exc
        if not decimal_amount.is_finite() or decimal_amount <= 0:
            raise BankDemoDomainError("Amount must be greater than zero.")
        if not 8 <= len(client_idempotency_key) <= 200:
            raise BankDemoDomainError("client_idempotency_key must contain 8 to 200 characters.")
        if currency != "INR" or rail != "DEMO_BANK_RAIL":
            raise BankDemoDomainError("The demo supports only INR over DEMO_BANK_RAIL.")
        action = {
            "tenant_id": scope.tenant_id,
            "user_id": scope.user_id,
            "source_account_token": source_account_token,
            "beneficiary_token": beneficiary_token,
            "amount": str(decimal_amount),
            "currency": currency,
            "rail": rail,
            "purpose": scope.purpose,
            "client_idempotency_key": client_idempotency_key,
        }
        action_hash = self._hash(action)
        async with session() as db:
            await self._require_consent(db, scope)
            existing = await db.scalar(
                select(PreparedTransfer).where(
                    PreparedTransfer.tenant_id == scope.tenant_id,
                    PreparedTransfer.idempotency_key == client_idempotency_key,
                )
            )
            if existing is not None:
                if existing.canonical_action_hash != action_hash:
                    raise BankDemoDomainError(
                        "The idempotency key was already used for a different preparation."
                    )
                self._audit(
                    db,
                    scope,
                    "IDEMPOTENT_REPLAY",
                    {"proposed_action_id": existing.proposed_action_id},
                )
                return self._prepared_projection(existing)
            account = await self._account(db, scope, source_account_token)
            beneficiary = await db.scalar(
                select(Beneficiary).where(
                    Beneficiary.beneficiary_token == beneficiary_token,
                    Beneficiary.tenant_id == scope.tenant_id,
                )
            )
            if beneficiary is None or not beneficiary.verified or beneficiary.status != "ACTIVE":
                raise BankDemoDomainError("Beneficiary is not verified and active.")
            if decimal_amount > account.per_transfer_limit:
                raise BankDemoDomainError("Amount exceeds the synthetic per-transfer limit.")
            now = datetime.now(UTC)
            pending_amount = await db.scalar(
                select(func.coalesce(func.sum(PreparedTransfer.amount), 0)).where(
                    PreparedTransfer.tenant_id == scope.tenant_id,
                    PreparedTransfer.user_id == scope.user_id,
                    PreparedTransfer.source_account_token == source_account_token,
                    PreparedTransfer.status == "READY_FOR_GUARDIAN",
                    PreparedTransfer.expires_at > now,
                )
            )
            proposed_total = Decimal(pending_amount or 0) + decimal_amount
            if proposed_total > account.available_balance:
                raise BankDemoDomainError(
                    "Active preparations plus this amount exceed the synthetic available balance."
                )
            if proposed_total > account.daily_limit:
                raise BankDemoDomainError(
                    "Active preparations plus this amount exceed the synthetic daily limit."
                )
            value = PreparedTransfer(
                proposed_action_id=f"act_demo_{uuid4().hex[:16]}",
                tenant_id=scope.tenant_id,
                user_id=scope.user_id,
                source_account_token=source_account_token,
                beneficiary_token=beneficiary_token,
                amount=decimal_amount,
                currency=currency,
                rail=rail,
                purpose=scope.purpose,
                idempotency_key=client_idempotency_key,
                canonical_action_hash=action_hash,
                status="READY_FOR_GUARDIAN",
                expires_at=now + timedelta(minutes=15),
            )
            db.add(value)
            self._audit(
                db,
                scope,
                "PREPARED",
                {"proposed_action_id": value.proposed_action_id, "action_hash": action_hash},
            )
            await db.flush()
            return self._prepared_projection(value)

    async def transfer_status(self, scope: RuntimeScope, proposed_action_id: str) -> dict[str, Any]:
        async with session() as db:
            value = await db.scalar(
                select(PreparedTransfer).where(
                    PreparedTransfer.proposed_action_id == proposed_action_id,
                    PreparedTransfer.tenant_id == scope.tenant_id,
                    PreparedTransfer.user_id == scope.user_id,
                )
            )
            if value is None:
                raise BankDemoDomainError("Prepared transfer was not found in the signed scope.")
            expires_at = value.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if value.status == "READY_FOR_GUARDIAN" and expires_at <= datetime.now(UTC):
                value.status = "EXPIRED"
            result = self._prepared_projection(value)
            execution = await db.scalar(
                select(TransferExecution).where(
                    TransferExecution.proposed_action_id == proposed_action_id,
                    TransferExecution.tenant_id == scope.tenant_id,
                )
            )
            if execution is not None:
                ledger_entries = (
                    await db.scalars(
                        select(LedgerEntry)
                        .where(LedgerEntry.execution_id == execution.execution_id)
                        .order_by(LedgerEntry.line_number)
                    )
                ).all()
                result["execution"] = self._execution_projection(execution, ledger_entries)
            self._audit(db, scope, "SUCCESS", {"proposed_action_id": proposed_action_id})
            return result

    async def execute_transfer(
        self,
        scope: RuntimeScope,
        proposed_action_id: str,
        client_idempotency_key: str,
    ) -> dict[str, Any]:
        if (
            not scope.authorization_consumed
            or not scope.authorization_id
            or not scope.guardian_decision_id
        ):
            raise BankDemoSecurityError(
                "A consumed exact-action Guardian authorization is required for execution."
            )
        if not 8 <= len(client_idempotency_key) <= 200:
            raise BankDemoDomainError("client_idempotency_key must contain 8 to 200 characters.")

        result: dict[str, Any]
        async with session() as db:
            prepared = await db.scalar(
                select(PreparedTransfer)
                .where(
                    PreparedTransfer.proposed_action_id == proposed_action_id,
                    PreparedTransfer.tenant_id == scope.tenant_id,
                    PreparedTransfer.user_id == scope.user_id,
                )
                .with_for_update()
            )
            if prepared is None:
                raise BankDemoDomainError("Prepared transfer was not found in the signed scope.")

            existing = await db.scalar(
                select(TransferExecution).where(
                    TransferExecution.proposed_action_id == proposed_action_id,
                    TransferExecution.tenant_id == scope.tenant_id,
                )
            )
            if existing is not None:
                if (
                    existing.idempotency_key != client_idempotency_key
                    or existing.canonical_action_hash != prepared.canonical_action_hash
                ):
                    raise BankDemoDomainError(
                        "The transfer was already executed with different idempotency data."
                    )
                entries = (
                    await db.scalars(
                        select(LedgerEntry)
                        .where(LedgerEntry.execution_id == existing.execution_id)
                        .order_by(LedgerEntry.line_number)
                    )
                ).all()
                self._audit(
                    db,
                    scope,
                    "IDEMPOTENT_REPLAY",
                    {"execution_id": existing.execution_id},
                )
                return self._execution_projection(existing, entries)

            authorization_replay = await db.scalar(
                select(TransferExecution).where(
                    TransferExecution.authorization_id == scope.authorization_id
                )
            )
            if authorization_replay is not None:
                raise BankDemoSecurityError(
                    "The Guardian authorization was already bound to another execution."
                )
            if prepared.idempotency_key != client_idempotency_key:
                raise BankDemoDomainError(
                    "Execution idempotency key does not match the prepared action."
                )
            expires_at = prepared.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= datetime.now(UTC):
                prepared.status = "EXPIRED"
                raise BankDemoDomainError("The prepared transfer has expired.")
            if prepared.status != "READY_FOR_GUARDIAN":
                raise BankDemoDomainError(
                    f"Prepared transfer cannot execute from status {prepared.status}."
                )

            expected_hash = self._hash(self._action_document(prepared))
            if not hmac.compare_digest(expected_hash, prepared.canonical_action_hash):
                raise BankDemoSecurityError(
                    "The stored transfer no longer matches its canonical action hash."
                )

            account = await db.scalar(
                select(Account)
                .where(
                    Account.account_token == prepared.source_account_token,
                    Account.tenant_id == scope.tenant_id,
                    Account.user_id == scope.user_id,
                    Account.status == "ACTIVE",
                )
                .with_for_update()
            )
            if account is None:
                raise BankDemoDomainError("Source account is not active in the signed scope.")
            beneficiary = await db.scalar(
                select(Beneficiary).where(
                    Beneficiary.beneficiary_token == prepared.beneficiary_token,
                    Beneficiary.tenant_id == scope.tenant_id,
                )
            )
            if beneficiary is None or not beneficiary.verified or beneficiary.status != "ACTIVE":
                raise BankDemoDomainError("Beneficiary is no longer verified and active.")
            if prepared.currency != account.currency or prepared.currency != beneficiary.currency:
                raise BankDemoDomainError(
                    "Transfer currency no longer matches the account records."
                )
            if prepared.amount > account.per_transfer_limit:
                raise BankDemoDomainError("Amount exceeds the current per-transfer limit.")
            if prepared.amount > account.available_balance:
                raise BankDemoDomainError("Available balance is insufficient at execution time.")

            day_start = datetime.combine(date.today(), datetime.min.time(), tzinfo=UTC)
            executed_today = await db.scalar(
                select(func.coalesce(func.sum(PreparedTransfer.amount), 0))
                .join(
                    TransferExecution,
                    TransferExecution.proposed_action_id == PreparedTransfer.proposed_action_id,
                )
                .where(
                    PreparedTransfer.tenant_id == scope.tenant_id,
                    PreparedTransfer.source_account_token == account.account_token,
                    TransferExecution.executed_at >= day_start,
                    TransferExecution.status.in_(["ACCEPTED", "SETTLED"]),
                )
            )
            if Decimal(executed_today or 0) + prepared.amount > account.daily_limit:
                raise BankDemoDomainError("Amount exceeds the remaining daily execution limit.")

            now = datetime.now(UTC)
            execution_id = f"exec_demo_{uuid4().hex[:16]}"
            bank_reference = f"DBR-{now:%Y%m%d}-{uuid4().hex[:10].upper()}"
            journal_id = f"jrnl_demo_{uuid4().hex[:16]}"
            execution = TransferExecution(
                execution_id=execution_id,
                proposed_action_id=prepared.proposed_action_id,
                tenant_id=scope.tenant_id,
                user_id=scope.user_id,
                idempotency_key=client_idempotency_key,
                canonical_action_hash=prepared.canonical_action_hash,
                guardian_decision_id=scope.guardian_decision_id,
                authorization_id=scope.authorization_id,
                request_hash=scope.request_hash,
                bank_reference=bank_reference,
                status="SETTLED",
                reconciliation_required=False,
                executed_at=now,
                settled_at=now,
            )
            account.current_balance -= prepared.amount
            account.available_balance -= prepared.amount
            prepared.status = "SETTLED"
            db.add(execution)
            db.add(
                Transaction(
                    id=str(uuid4()),
                    account_token=account.account_token,
                    booked_on=date.today(),
                    direction="DEBIT",
                    amount=prepared.amount,
                    currency=prepared.currency,
                    category="GUARDIAN_AUTHORIZED_TRANSFER",
                    description=f"Synthetic transfer to {beneficiary.owner_name}",
                    reference=bank_reference,
                )
            )
            ledger_entries = [
                LedgerEntry(
                    id=str(uuid4()),
                    execution_id=execution_id,
                    journal_id=journal_id,
                    line_number=1,
                    ledger_account="DISBURSEMENT_CLEARING",
                    entry_type="DEBIT",
                    amount=prepared.amount,
                    currency=prepared.currency,
                ),
                LedgerEntry(
                    id=str(uuid4()),
                    execution_id=execution_id,
                    journal_id=journal_id,
                    line_number=2,
                    ledger_account="BANK_CASH_CONTROL",
                    entry_type="CREDIT",
                    amount=prepared.amount,
                    currency=prepared.currency,
                ),
            ]
            db.add_all(ledger_entries)
            self._audit(
                db,
                scope,
                "SETTLED",
                {
                    "proposed_action_id": prepared.proposed_action_id,
                    "execution_id": execution_id,
                    "bank_reference": bank_reference,
                    "guardian_decision_id": scope.guardian_decision_id,
                    "authorization_id": scope.authorization_id,
                    "journal_id": journal_id,
                    "resulting_available_balance": str(account.available_balance),
                },
            )
            await db.flush()
            result = self._execution_projection(execution, ledger_entries)
            result["resulting_available_balance"] = str(account.available_balance)
        demo_events.publish(
            "transfer.settled",
            {
                "proposed_action_id": proposed_action_id,
                "execution_id": result["execution_id"],
                "status": result["status"],
            },
        )
        return result

    @staticmethod
    async def _account(db: Any, scope: RuntimeScope, token: str) -> Account:
        account = await db.scalar(
            select(Account).where(
                Account.account_token == token,
                Account.tenant_id == scope.tenant_id,
                Account.user_id == scope.user_id,
                Account.status == "ACTIVE",
            )
        )
        if account is None:
            raise BankDemoDomainError("Account was not found in the signed tenant/user scope.")
        return account

    @staticmethod
    async def _require_consent(db: Any, scope: RuntimeScope) -> Consent:
        value = await db.scalar(
            select(Consent).where(
                Consent.tenant_id == scope.tenant_id,
                Consent.user_id == scope.user_id,
                Consent.status == "ACTIVE",
            )
        )
        if value is None:
            raise BankDemoSecurityError("An active synthetic evidence consent is required.")
        valid_until = value.valid_until
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=UTC)
        if valid_until <= datetime.now(UTC):
            raise BankDemoSecurityError("The synthetic evidence consent has expired.")
        if value.purpose_prefix and not scope.purpose.startswith(value.purpose_prefix):
            raise BankDemoSecurityError("Purpose is outside the synthetic consent scope.")
        return value

    @staticmethod
    def _account_projection(account: Account) -> dict[str, Any]:
        return {
            "account_token": account.account_token,
            "display_name": account.display_name,
            "masked_number": account.masked_number,
            "account_type": account.account_type,
            "currency": account.currency,
            "status": account.status,
        }

    @staticmethod
    def _prepared_projection(value: PreparedTransfer) -> dict[str, Any]:
        expires = value.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        return {
            "status": value.status,
            "proposed_action_id": value.proposed_action_id,
            "canonical_action_hash": value.canonical_action_hash,
            "source_account_token": value.source_account_token,
            "beneficiary_token": value.beneficiary_token,
            "amount": str(value.amount),
            "currency": value.currency,
            "rail": value.rail,
            "purpose": value.purpose,
            "expires_at": expires.isoformat(),
            "execution_available": True,
            "security_flags": ["SYNTHETIC_DATA", "GUARDIAN_AUTH_REQUIRED"],
        }

    @staticmethod
    def _action_document(value: PreparedTransfer) -> dict[str, Any]:
        return {
            "tenant_id": value.tenant_id,
            "user_id": value.user_id,
            "source_account_token": value.source_account_token,
            "beneficiary_token": value.beneficiary_token,
            "amount": str(value.amount),
            "currency": value.currency,
            "rail": value.rail,
            "purpose": value.purpose,
            "client_idempotency_key": value.idempotency_key,
        }

    @staticmethod
    def _execution_projection(
        value: TransferExecution, ledger_entries: list[LedgerEntry]
    ) -> dict[str, Any]:
        executed_at = value.executed_at
        if executed_at.tzinfo is None:
            executed_at = executed_at.replace(tzinfo=UTC)
        settled_at = value.settled_at
        if settled_at is not None and settled_at.tzinfo is None:
            settled_at = settled_at.replace(tzinfo=UTC)
        return {
            "status": value.status,
            "execution_id": value.execution_id,
            "proposed_action_id": value.proposed_action_id,
            "bank_reference": value.bank_reference,
            "canonical_action_hash": value.canonical_action_hash,
            "guardian_decision_id": value.guardian_decision_id,
            "authorization_id": value.authorization_id,
            "executed_at": executed_at.isoformat(),
            "settled_at": settled_at.isoformat() if settled_at else None,
            "reconciliation_required": value.reconciliation_required,
            "ledger": [
                {
                    "journal_id": entry.journal_id,
                    "line_number": entry.line_number,
                    "ledger_account": entry.ledger_account,
                    "entry_type": entry.entry_type,
                    "amount": str(entry.amount),
                    "currency": entry.currency,
                }
                for entry in ledger_entries
            ],
            "security_flags": [
                "SYNTHETIC_DATA",
                "GUARDIAN_AUTHORIZATION_CONSUMED",
                "IDEMPOTENT_EXECUTION",
                "LEDGER_BALANCED",
            ],
        }

    def _receipt(self, scope: RuntimeScope, kind: str, refs: list[str]) -> str:
        body = {"call_id": scope.call_id, "kind": kind, "refs": refs}
        signature = hmac.new(
            get_settings().mcp_token.get_secret_value().encode(),
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()[:24]
        return f"evr_demo_{signature}"

    @staticmethod
    def _hash(value: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()

    @staticmethod
    def _audit(db: Any, scope: RuntimeScope, outcome: str, detail: dict[str, Any]) -> None:
        db.add(
            AuditEvent(
                id=str(uuid4()),
                tenant_id=scope.tenant_id,
                user_id=scope.user_id,
                call_id=scope.call_id,
                tool_name=scope.canonical_name,
                purpose=scope.purpose,
                outcome=outcome,
                detail=json.dumps(detail, sort_keys=True, default=str),
            )
        )


bank_service = BankDemoService()
