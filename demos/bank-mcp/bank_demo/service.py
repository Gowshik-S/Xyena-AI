import hashlib
import hmac
import json
import secrets
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select

from .database import session
from .models import (
    AAConsent, Account, AccountHold, AuditEvent, BankOutboxEvent, Beneficiary,
    FinancialInformationRequest, PreparedBeneficiaryChange, PreparedReversal,
    PreparedTransfer, Transaction, TransferExecution,
)
from .security import BankDemoSecurityError, RuntimeScope
from .settings import get_settings


class BankDemoDomainError(RuntimeError):
    pass


class BankDemoService:
    """Synthetic bank and AA service with hash-bound, replay-safe state changes."""

    async def create_consent(self, scope: RuntimeScope, account_tokens: list[str],
                             information_types: list[str], valid_days: int,
                             client_idempotency_key: str) -> dict[str, Any]:
        info = sorted(set(item.upper() for item in information_types))
        if not info or set(info) - {"ACCOUNT", "BALANCE", "TRANSACTIONS"}:
            raise BankDemoDomainError("Use ACCOUNT, BALANCE or TRANSACTIONS information types.")
        if not 1 <= valid_days <= 90:
            raise BankDemoDomainError("valid_days must be between 1 and 90.")
        action_hash = self._hash({"tenant_id": scope.tenant_id, "user_id": scope.user_id,
                                  "purpose": scope.purpose,
                                  "account_tokens": sorted(set(account_tokens)),
                                  "information_types": info, "valid_days": valid_days,
                                  "idempotency_key": client_idempotency_key})
        now = datetime.now(UTC)
        async with session() as db:
            existing = await db.scalar(select(AAConsent).where(
                AAConsent.tenant_id == scope.tenant_id,
                AAConsent.idempotency_key == client_idempotency_key))
            if existing:
                if existing.request_hash != action_hash:
                    raise BankDemoDomainError("Consent idempotency parameter drift detected.")
                return self._consent_projection(existing)
            for token in sorted(set(account_tokens)):
                await self._account(db, scope, token)
            value = AAConsent(
                consent_id=f"aac_{uuid4().hex[:18]}", tenant_id=scope.tenant_id,
                user_id=scope.user_id, purpose=scope.purpose,
                account_tokens=sorted(set(account_tokens)), information_types=info,
                idempotency_key=client_idempotency_key, request_hash=action_hash,
                status="ACTIVE", valid_from=now, valid_until=now + timedelta(days=valid_days),
            )
            db.add(value)
            self._event(db, scope.tenant_id, "AA_CONSENT", value.consent_id,
                        "bank.aa.consent.created", self._consent_projection(value))
            self._audit(db, scope, "CREATED", {"consent_id": value.consent_id})
            await db.flush()
            return self._consent_projection(value)

    async def get_consent(self, scope: RuntimeScope, consent_id: str) -> dict[str, Any]:
        async with session() as db:
            value = await self._consent(db, scope, consent_id, False)
            self._audit(db, scope, "SUCCESS", {"consent_id": consent_id})
            return self._consent_projection(value)

    async def revoke_consent(self, scope: RuntimeScope, consent_id: str) -> dict[str, Any]:
        async with session() as db:
            value = await self._consent(db, scope, consent_id, False)
            if value.status == "ACTIVE":
                value.status, value.revoked_at, value.version = "REVOKED", datetime.now(UTC), value.version + 1
                self._event(db, scope.tenant_id, "AA_CONSENT", consent_id,
                            "bank.aa.consent.revoked", {"consent_id": consent_id})
            self._audit(db, scope, "REVOKED", {"consent_id": consent_id})
            return self._consent_projection(value)

    async def fetch_information(self, scope: RuntimeScope, consent_id: str,
                                information_type: str, account_token: str,
                                client_idempotency_key: str,
                                from_date: date | None = None,
                                to_date: date | None = None) -> dict[str, Any]:
        kind = information_type.upper()
        if kind not in {"ACCOUNT", "BALANCE", "TRANSACTIONS"}:
            raise BankDemoDomainError("Unsupported financial information type.")
        action = {"consent_id": consent_id, "information_type": kind,
                  "account_token": account_token, "from_date": from_date,
                  "to_date": to_date, "idempotency_key": client_idempotency_key}
        action_hash = self._hash(action)
        async with session() as db:
            consent = await self._consent(db, scope, consent_id)
            if account_token not in consent.account_tokens or kind not in consent.information_types:
                raise BankDemoSecurityError("Requested information is outside the AA consent scope.")
            if consent.purpose and scope.purpose != consent.purpose:
                raise BankDemoSecurityError("Purpose does not match the AA consent.")
            existing = await db.scalar(select(FinancialInformationRequest).where(
                FinancialInformationRequest.tenant_id == scope.tenant_id,
                FinancialInformationRequest.idempotency_key == client_idempotency_key))
            if existing and existing.request_hash != action_hash:
                raise BankDemoDomainError("The FI idempotency key has different parameters.")
            account = await self._account(db, scope, account_token)
            if kind == "ACCOUNT":
                payload: Any = self._account_projection(account)
            elif kind == "BALANCE":
                payload = self._balance_projection(account)
            else:
                start, end = from_date or date.today() - timedelta(days=30), to_date or date.today()
                if start > end or (end - start).days > 90:
                    raise BankDemoDomainError("Transactions require a valid 90-day window.")
                rows = (await db.scalars(select(Transaction).where(
                    Transaction.account_token == account_token,
                    Transaction.booked_on >= start, Transaction.booked_on <= end)
                    .order_by(Transaction.booked_on.desc()).limit(100))).all()
                payload = [self._transaction_projection(row) for row in rows]
            receipt = self._receipt(scope, "aa.fetch_information", [consent_id, account_token, action_hash])
            if existing is None:
                existing = FinancialInformationRequest(
                    request_id=f"fir_{uuid4().hex[:18]}", tenant_id=scope.tenant_id,
                    user_id=scope.user_id, consent_id=consent_id,
                    information_type=kind, account_token=account_token,
                    from_date=from_date, to_date=to_date,
                    idempotency_key=client_idempotency_key, request_hash=action_hash,
                    evidence_receipt_id=receipt, status="COMPLETED", completed_at=datetime.now(UTC))
                db.add(existing)
            self._audit(db, scope, "SUCCESS", {"request_id": existing.request_id})
            return {"status": "COMPLETED", "request_id": existing.request_id,
                    "consent_id": consent_id, "information_type": kind,
                    "data": payload, "evidence_receipt_id": receipt,
                    "security_flags": ["SYNTHETIC_DATA", "CONSENT_SCOPED"]}

    async def list_accounts(self, scope: RuntimeScope) -> dict[str, Any]:
        async with session() as db:
            await self._require_any_consent(db, scope, "ACCOUNT")
            rows = (await db.scalars(select(Account).where(
                Account.tenant_id == scope.tenant_id, Account.user_id == scope.user_id,
                Account.status == "ACTIVE"))).all()
            self._audit(db, scope, "SUCCESS", {"account_count": len(rows)})
            return {"status": "SUCCESS", "accounts": [self._account_projection(v) for v in rows],
                    "evidence_receipt_id": self._receipt(scope, "accounts.list", [v.account_token for v in rows]),
                    "security_flags": ["SYNTHETIC_DATA", "CONSENT_SCOPED"]}

    async def get_account(self, scope: RuntimeScope, account_token: str) -> dict[str, Any]:
        async with session() as db:
            await self._require_any_consent(db, scope, "ACCOUNT", account_token)
            value = await self._account(db, scope, account_token)
            self._audit(db, scope, "SUCCESS", {"account_token": account_token})
            return {**self._account_projection(value), **self._balance_projection(value),
                    "evidence_receipt_id": self._receipt(scope, "accounts.get", [account_token]),
                    "security_flags": ["SYNTHETIC_DATA", "CONSENT_SCOPED"]}

    async def get_balance(self, scope: RuntimeScope, account_token: str) -> dict[str, Any]:
        async with session() as db:
            await self._require_any_consent(db, scope, "BALANCE", account_token)
            value = await self._account(db, scope, account_token)
            self._audit(db, scope, "SUCCESS", {"account_token": account_token})
            return {"status": "SUCCESS", **self._balance_projection(value),
                    "evidence_receipt_id": self._receipt(scope, "accounts.get_balance", [account_token, str(value.available_balance)]),
                    "security_flags": ["SYNTHETIC_DATA", "CONSENT_SCOPED"]}

    async def list_transactions(self, scope: RuntimeScope, account_token: str,
                                from_date: date, to_date: date, limit: int) -> dict[str, Any]:
        if from_date > to_date or (to_date - from_date).days > 90:
            raise BankDemoDomainError("A valid transaction window of at most 90 days is required.")
        async with session() as db:
            await self._require_any_consent(db, scope, "TRANSACTIONS", account_token)
            await self._account(db, scope, account_token)
            rows = (await db.scalars(select(Transaction).where(
                Transaction.account_token == account_token, Transaction.booked_on >= from_date,
                Transaction.booked_on <= to_date).order_by(Transaction.booked_on.desc())
                .limit(max(1, min(limit, 100))))).all()
            self._audit(db, scope, "SUCCESS", {"transaction_count": len(rows)})
            return {"status": "SUCCESS", "account_token": account_token,
                    "from_date": from_date.isoformat(), "to_date": to_date.isoformat(),
                    "transactions": [self._transaction_projection(v) for v in rows],
                    "evidence_receipt_id": self._receipt(scope, "transactions.list", [v.id for v in rows]),
                    "security_flags": ["SYNTHETIC_DATA", "CONSENT_SCOPED"]}

    async def verify_beneficiary(self, scope: RuntimeScope, beneficiary_token: str) -> dict[str, Any]:
        async with session() as db:
            value = await self._beneficiary(db, scope, beneficiary_token, False)
            self._audit(db, scope, "SUCCESS", {"beneficiary_token": beneficiary_token})
            return {"status": "SUCCESS", "beneficiary_token": value.beneficiary_token,
                    "owner_name": value.owner_name, "masked_account": value.masked_account,
                    "bank_name": value.bank_name, "currency": value.currency,
                    "verified": value.verified, "beneficiary_status": value.status,
                    "evidence_receipt_id": self._receipt(scope, "beneficiaries.verify", [beneficiary_token, value.status]),
                    "security_flags": ["SYNTHETIC_DATA"] + ([] if value.verified else ["BENEFICIARY_UNVERIFIED"])}

    async def get_limits(self, scope: RuntimeScope, account_token: str) -> dict[str, Any]:
        async with session() as db:
            account = await self._account(db, scope, account_token)
            self._audit(db, scope, "SUCCESS", {"account_token": account_token})
            return {"status": "SUCCESS", "account_token": account_token, "currency": account.currency,
                    "per_transfer": str(account.per_transfer_limit), "per_day": str(account.daily_limit),
                    "allowed_rails": ["DEMO_BANK_RAIL"], "execution_available": True,
                    "execution_boundary": "GUARDIAN_AUTHORIZED_MCP_ONLY", "security_flags": ["SYNTHETIC_DATA"]}

    async def prepare_transfer(self, scope: RuntimeScope, source_account_token: str,
                               beneficiary_token: str, amount: str, currency: str,
                               rail: str, client_idempotency_key: str) -> dict[str, Any]:
        value_amount = self._amount(amount)
        self._validate_payment(currency, rail, client_idempotency_key)
        action = {"tenant_id": scope.tenant_id, "user_id": scope.user_id,
                  "source_account_token": source_account_token, "beneficiary_token": beneficiary_token,
                  "amount": str(value_amount), "currency": currency, "rail": rail,
                  "purpose": scope.purpose, "client_idempotency_key": client_idempotency_key}
        action_hash = self._hash(action)
        async with session() as db:
            existing = await db.scalar(select(PreparedTransfer).where(
                PreparedTransfer.tenant_id == scope.tenant_id,
                PreparedTransfer.idempotency_key == client_idempotency_key))
            if existing:
                if existing.canonical_action_hash != action_hash:
                    raise BankDemoDomainError("The idempotency key is bound to a different transfer.")
                return self._prepared_projection(existing)
            account = await self._account(db, scope, source_account_token)
            await self._beneficiary(db, scope, beneficiary_token)
            await self._check_payment_capacity(db, account, value_amount)
            now = datetime.now(UTC)
            value = PreparedTransfer(
                proposed_action_id=f"act_{uuid4().hex[:18]}", tenant_id=scope.tenant_id,
                user_id=scope.user_id, source_account_token=source_account_token,
                beneficiary_token=beneficiary_token, amount=value_amount, currency=currency,
                rail=rail, purpose=scope.purpose, idempotency_key=client_idempotency_key,
                canonical_action_hash=action_hash, status="READY_FOR_GUARDIAN",
                expires_at=now + timedelta(minutes=15))
            db.add(value)
            self._audit(db, scope, "PREPARED", {"proposed_action_id": value.proposed_action_id, "action_hash": action_hash})
            await db.flush()
            return self._prepared_projection(value)

    async def execute_transfer(self, scope: RuntimeScope, proposed_action_id: str,
                               canonical_action_hash: str,
                               execution_id: str) -> dict[str, Any]:
        async with session() as db:
            prior = await db.scalar(select(TransferExecution).where(
                TransferExecution.tenant_id == scope.tenant_id,
                TransferExecution.execution_id == execution_id))
            if prior:
                if prior.canonical_action_hash != canonical_action_hash:
                    raise BankDemoDomainError("execution_id is bound to another action hash.")
                return self._execution_projection(prior)
            prior_action = await db.scalar(select(TransferExecution).where(
                TransferExecution.tenant_id == scope.tenant_id,
                TransferExecution.proposed_action_id == proposed_action_id))
            if prior_action:
                if prior_action.canonical_action_hash != canonical_action_hash:
                    raise BankDemoDomainError("Prepared action is already bound to another hash.")
                return self._execution_projection(prior_action)
            replay = await db.scalar(select(TransferExecution).where(
                TransferExecution.tenant_id == scope.tenant_id,
                TransferExecution.guardian_call_id == scope.call_id))
            if replay:
                raise BankDemoSecurityError("Guardian call id has already changed bank state.")
            prepared = await db.scalar(select(PreparedTransfer).where(
                PreparedTransfer.proposed_action_id == proposed_action_id,
                PreparedTransfer.tenant_id == scope.tenant_id,
                PreparedTransfer.user_id == scope.user_id))
            if prepared is None or prepared.canonical_action_hash != canonical_action_hash:
                raise BankDemoSecurityError("Prepared action and canonical hash do not match.")
            if prepared.status != "READY_FOR_GUARDIAN" or self._aware(prepared.expires_at) <= datetime.now(UTC):
                raise BankDemoDomainError("Prepared transfer is not executable.")
            account = await self._account(db, scope, prepared.source_account_token)
            await self._beneficiary(db, scope, prepared.beneficiary_token)
            await self._check_payment_capacity(db, account, prepared.amount, prepared.proposed_action_id)
            reference = f"XY{secrets.token_hex(4).upper()}"[:10]
            account.current_balance -= prepared.amount
            account.available_balance -= prepared.amount
            prepared.status = "SETTLED"
            value = TransferExecution(
                id=str(uuid4()), execution_id=execution_id, tenant_id=scope.tenant_id,
                user_id=scope.user_id, proposed_action_id=proposed_action_id,
                canonical_action_hash=canonical_action_hash, guardian_decision_id=scope.guardian_decision_id,
                guardian_call_id=scope.call_id, request_hash=scope.request_hash,
                amount=prepared.amount, currency=prepared.currency, bank_reference=reference,
                status="SETTLED", settled_at=datetime.now(UTC))
            db.add_all([value, Transaction(
                id=str(uuid4()), account_token=account.account_token, booked_on=date.today(),
                direction="DEBIT", amount=prepared.amount, currency=prepared.currency,
                category="GUARDIAN_PAYMENT", description="Guardian-authorized synthetic transfer",
                reference=reference)])
            payload = self._execution_projection(value)
            self._event(db, scope.tenant_id, "TRANSFER", execution_id, "bank.transfer.settled", payload)
            self._audit(db, scope, "SETTLED", payload)
            return payload

    async def transfer_status(self, scope: RuntimeScope, proposed_action_id: str) -> dict[str, Any]:
        async with session() as db:
            execution = await db.scalar(select(TransferExecution).where(
                TransferExecution.proposed_action_id == proposed_action_id,
                TransferExecution.tenant_id == scope.tenant_id))
            if execution:
                return self._execution_projection(execution)
            value = await db.scalar(select(PreparedTransfer).where(
                PreparedTransfer.proposed_action_id == proposed_action_id,
                PreparedTransfer.tenant_id == scope.tenant_id,
                PreparedTransfer.user_id == scope.user_id))
            if value is None:
                raise BankDemoDomainError("Transfer was not found in the signed scope.")
            if value.status == "READY_FOR_GUARDIAN" and self._aware(value.expires_at) <= datetime.now(UTC):
                value.status = "EXPIRED"
            return self._prepared_projection(value)

    async def place_hold(self, scope: RuntimeScope, account_token: str, amount: str,
                         currency: str, client_idempotency_key: str) -> dict[str, Any]:
        value_amount = self._amount(amount)
        async with session() as db:
            existing = await db.scalar(select(AccountHold).where(
                AccountHold.tenant_id == scope.tenant_id,
                AccountHold.idempotency_key == client_idempotency_key))
            if existing:
                if existing.account_token != account_token or existing.amount != value_amount:
                    raise BankDemoDomainError("Hold idempotency parameter drift detected.")
                return self._hold_projection(existing)
            account = await self._account(db, scope, account_token)
            if currency != account.currency or value_amount > account.available_balance:
                raise BankDemoDomainError("Hold exceeds available balance or currency differs.")
            account.available_balance -= value_amount
            value = AccountHold(
                hold_id=f"hold_{uuid4().hex[:18]}", tenant_id=scope.tenant_id,
                user_id=scope.user_id, account_token=account_token, amount=value_amount,
                currency=currency, purpose=scope.purpose, idempotency_key=client_idempotency_key,
                guardian_call_id=scope.call_id, request_hash=scope.request_hash, status="ACTIVE")
            db.add(value)
            self._event(db, scope.tenant_id, "HOLD", value.hold_id, "bank.hold.placed", self._hold_projection(value))
            self._audit(db, scope, "PLACED", {"hold_id": value.hold_id})
            return self._hold_projection(value)

    async def release_hold(self, scope: RuntimeScope, hold_id: str) -> dict[str, Any]:
        async with session() as db:
            value = await db.scalar(select(AccountHold).where(
                AccountHold.hold_id == hold_id, AccountHold.tenant_id == scope.tenant_id,
                AccountHold.user_id == scope.user_id))
            if value is None:
                raise BankDemoDomainError("Hold was not found.")
            if value.status == "RELEASED":
                return self._hold_projection(value)
            if value.release_guardian_call_id:
                raise BankDemoSecurityError("Hold release was already consumed.")
            account = await self._account(db, scope, value.account_token)
            account.available_balance += value.amount
            value.status, value.released_at = "RELEASED", datetime.now(UTC)
            value.release_guardian_call_id = scope.call_id
            self._event(db, scope.tenant_id, "HOLD", hold_id, "bank.hold.released", self._hold_projection(value))
            self._audit(db, scope, "RELEASED", {"hold_id": hold_id})
            return self._hold_projection(value)

    async def prepare_beneficiary_change(self, scope: RuntimeScope, beneficiary_token: str,
                                         owner_name: str, masked_account: str, bank_name: str,
                                         currency: str, client_idempotency_key: str) -> dict[str, Any]:
        action = {"beneficiary_token": beneficiary_token, "owner_name": owner_name,
                  "masked_account": masked_account, "bank_name": bank_name,
                  "currency": currency, "idempotency_key": client_idempotency_key}
        action_hash = self._hash(action)
        async with session() as db:
            existing = await db.scalar(select(PreparedBeneficiaryChange).where(
                PreparedBeneficiaryChange.tenant_id == scope.tenant_id,
                PreparedBeneficiaryChange.idempotency_key == client_idempotency_key))
            if existing:
                if existing.canonical_action_hash != action_hash:
                    raise BankDemoDomainError("Beneficiary change parameter drift detected.")
                return self._beneficiary_change_projection(existing)
            value = PreparedBeneficiaryChange(
                change_id=f"bchg_{uuid4().hex[:18]}", tenant_id=scope.tenant_id,
                user_id=scope.user_id, beneficiary_token=beneficiary_token,
                requested_owner_name=owner_name, requested_masked_account=masked_account,
                requested_bank_name=bank_name, currency=currency,
                idempotency_key=client_idempotency_key, canonical_action_hash=action_hash,
                status="READY_FOR_GUARDIAN", expires_at=datetime.now(UTC) + timedelta(minutes=15))
            db.add(value)
            self._audit(db, scope, "PREPARED", {"change_id": value.change_id})
            return self._beneficiary_change_projection(value)

    async def execute_beneficiary_change(self, scope: RuntimeScope, change_id: str,
                                         canonical_action_hash: str) -> dict[str, Any]:
        async with session() as db:
            value = await db.scalar(select(PreparedBeneficiaryChange).where(
                PreparedBeneficiaryChange.change_id == change_id,
                PreparedBeneficiaryChange.tenant_id == scope.tenant_id))
            if value is None or value.canonical_action_hash != canonical_action_hash:
                raise BankDemoSecurityError("Beneficiary change hash mismatch.")
            if value.status == "EXECUTED":
                return self._beneficiary_change_projection(value)
            if value.status != "READY_FOR_GUARDIAN" or self._aware(value.expires_at) <= datetime.now(UTC):
                raise BankDemoDomainError("Beneficiary change is not executable.")
            target = await db.get(Beneficiary, value.beneficiary_token)
            if target is None:
                target = Beneficiary(beneficiary_token=value.beneficiary_token, tenant_id=scope.tenant_id,
                                     owner_name=value.requested_owner_name, masked_account=value.requested_masked_account,
                                     bank_name=value.requested_bank_name, currency=value.currency,
                                     verified=True, status="ACTIVE")
                db.add(target)
            else:
                if target.tenant_id != scope.tenant_id:
                    raise BankDemoSecurityError("Beneficiary belongs to another tenant.")
                target.owner_name, target.masked_account = value.requested_owner_name, value.requested_masked_account
                target.bank_name, target.currency = value.requested_bank_name, value.currency
                target.verified, target.status = True, "ACTIVE"
            value.status, value.guardian_call_id = "EXECUTED", scope.call_id
            payload = self._beneficiary_change_projection(value)
            payload["guardian_decision_id"] = scope.guardian_decision_id
            self._event(db, scope.tenant_id, "BENEFICIARY", value.beneficiary_token,
                        "bank.beneficiary.changed", payload)
            self._audit(db, scope, "EXECUTED", {"change_id": change_id})
            return payload

    async def prepare_reversal(self, scope: RuntimeScope, transfer_execution_id: str,
                               amount: str, reason: str, client_idempotency_key: str) -> dict[str, Any]:
        value_amount = self._amount(amount)
        action = {"transfer_execution_id": transfer_execution_id, "amount": str(value_amount),
                  "reason": reason, "idempotency_key": client_idempotency_key}
        action_hash = self._hash(action)
        async with session() as db:
            execution = await db.scalar(select(TransferExecution).where(
                TransferExecution.execution_id == transfer_execution_id,
                TransferExecution.tenant_id == scope.tenant_id, TransferExecution.status == "SETTLED"))
            if execution is None or value_amount > execution.amount:
                raise BankDemoDomainError("Settled transfer does not support this reversal amount.")
            existing = await db.scalar(select(PreparedReversal).where(
                PreparedReversal.tenant_id == scope.tenant_id,
                PreparedReversal.idempotency_key == client_idempotency_key))
            if existing:
                if existing.canonical_action_hash != action_hash:
                    raise BankDemoDomainError("Reversal parameter drift detected.")
                return self._reversal_projection(existing)
            value = PreparedReversal(
                reversal_id=f"rev_{uuid4().hex[:18]}", tenant_id=scope.tenant_id,
                user_id=scope.user_id, transfer_execution_id=transfer_execution_id,
                amount=value_amount, currency=execution.currency, reason=reason,
                idempotency_key=client_idempotency_key, canonical_action_hash=action_hash,
                status="REVIEW_REQUIRED", expires_at=datetime.now(UTC) + timedelta(hours=1))
            db.add(value)
            self._audit(db, scope, "PREPARED", {"reversal_id": value.reversal_id})
            return self._reversal_projection(value)

    async def execute_reversal(self, scope: RuntimeScope, reversal_id: str,
                               canonical_action_hash: str, reviewer_approval_id: str,
                               ) -> dict[str, Any]:
        if not reviewer_approval_id.strip():
            raise BankDemoSecurityError("A reviewer approval id is required for reversal.")
        async with session() as db:
            value = await db.scalar(select(PreparedReversal).where(
                PreparedReversal.reversal_id == reversal_id,
                PreparedReversal.tenant_id == scope.tenant_id))
            if value is None or value.canonical_action_hash != canonical_action_hash:
                raise BankDemoSecurityError("Reversal hash mismatch.")
            if value.status == "SETTLED":
                return self._reversal_projection(value)
            if value.status != "REVIEW_REQUIRED" or self._aware(value.expires_at) <= datetime.now(UTC):
                raise BankDemoDomainError("Reversal is not executable.")
            execution = await db.scalar(select(TransferExecution).where(
                TransferExecution.execution_id == value.transfer_execution_id,
                TransferExecution.tenant_id == scope.tenant_id))
            if execution is None:
                raise BankDemoDomainError("Original transfer execution was not found.")
            prepared = await db.get(PreparedTransfer, execution.proposed_action_id)
            account = await self._account(db, scope, prepared.source_account_token)
            reference = f"RV{secrets.token_hex(4).upper()}"[:10]
            account.current_balance += value.amount
            account.available_balance += value.amount
            value.status, value.reviewer_approval_id = "SETTLED", reviewer_approval_id
            value.guardian_call_id, value.bank_reference = scope.call_id, reference
            db.add(Transaction(id=str(uuid4()), account_token=account.account_token,
                               booked_on=date.today(), direction="CREDIT", amount=value.amount,
                               currency=value.currency, category="PAYMENT_REVERSAL",
                               description="Approved compensating bank reversal", reference=reference))
            payload = self._reversal_projection(value)
            payload["guardian_decision_id"] = scope.guardian_decision_id
            self._event(db, scope.tenant_id, "REVERSAL", reversal_id, "bank.reversal.settled", payload)
            self._audit(db, scope, "SETTLED", {"reversal_id": reversal_id})
            return payload

    @staticmethod
    async def _account(db: Any, scope: RuntimeScope, token: str) -> Account:
        value = await db.scalar(select(Account).where(
            Account.account_token == token, Account.tenant_id == scope.tenant_id,
            Account.user_id == scope.user_id, Account.status == "ACTIVE"))
        if value is None:
            raise BankDemoDomainError("Account was not found in the signed tenant/user scope.")
        return value

    @staticmethod
    async def _beneficiary(db: Any, scope: RuntimeScope, token: str, active: bool = True) -> Beneficiary:
        value = await db.scalar(select(Beneficiary).where(
            Beneficiary.beneficiary_token == token, Beneficiary.tenant_id == scope.tenant_id))
        if value is None or (active and (not value.verified or value.status != "ACTIVE")):
            raise BankDemoDomainError("Beneficiary is not verified and active in the signed tenant.")
        return value

    async def _consent(self, db: Any, scope: RuntimeScope, consent_id: str,
                       require_active: bool = True) -> AAConsent:
        value = await db.scalar(select(AAConsent).where(
            AAConsent.consent_id == consent_id, AAConsent.tenant_id == scope.tenant_id,
            AAConsent.user_id == scope.user_id))
        if value is None:
            raise BankDemoSecurityError("AA consent was not found in the signed scope.")
        if require_active and (value.status != "ACTIVE" or self._aware(value.valid_until) <= datetime.now(UTC)):
            raise BankDemoSecurityError("AA consent is not active.")
        return value

    async def _require_any_consent(self, db: Any, scope: RuntimeScope, kind: str,
                                   account_token: str | None = None) -> AAConsent:
        rows = (await db.scalars(select(AAConsent).where(
            AAConsent.tenant_id == scope.tenant_id, AAConsent.user_id == scope.user_id,
            AAConsent.status == "ACTIVE"))).all()
        for value in rows:
            if self._aware(value.valid_until) > datetime.now(UTC) and kind in value.information_types:
                if account_token is None or account_token in value.account_tokens:
                    return value
        raise BankDemoSecurityError("An active AA consent covering this information is required.")

    async def _check_payment_capacity(self, db: Any, account: Account, amount: Decimal,
                                      exclude_action: str | None = None) -> None:
        if amount > account.per_transfer_limit or amount > account.available_balance:
            raise BankDemoDomainError("Transfer exceeds bank limits or available balance.")
        query = select(func.coalesce(func.sum(PreparedTransfer.amount), 0)).where(
            PreparedTransfer.tenant_id == account.tenant_id,
            PreparedTransfer.source_account_token == account.account_token,
            PreparedTransfer.status == "READY_FOR_GUARDIAN",
            PreparedTransfer.expires_at > datetime.now(UTC))
        if exclude_action:
            query = query.where(PreparedTransfer.proposed_action_id != exclude_action)
        pending = Decimal(await db.scalar(query) or 0)
        if pending + amount > account.daily_limit:
            raise BankDemoDomainError("Transfer plus active preparations exceeds the daily limit.")

    @staticmethod
    def _amount(value: str) -> Decimal:
        try:
            amount = Decimal(value).quantize(Decimal("0.01"))
        except InvalidOperation as exc:
            raise BankDemoDomainError("Amount must be a decimal value.") from exc
        if not amount.is_finite() or amount <= 0:
            raise BankDemoDomainError("Amount must be greater than zero.")
        return amount

    @staticmethod
    def _validate_payment(currency: str, rail: str, key: str) -> None:
        if currency != "INR" or rail != "DEMO_BANK_RAIL":
            raise BankDemoDomainError("The synthetic bank supports INR over DEMO_BANK_RAIL.")
        if not 8 <= len(key) <= 200:
            raise BankDemoDomainError("client_idempotency_key must contain 8 to 200 characters.")

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    @staticmethod
    def _account_projection(value: Account) -> dict[str, Any]:
        return {"account_token": value.account_token, "display_name": value.display_name,
                "masked_number": value.masked_number, "account_type": value.account_type,
                "currency": value.currency, "status": value.status}

    @staticmethod
    def _balance_projection(value: Account) -> dict[str, Any]:
        return {"account_token": value.account_token, "currency": value.currency,
                "current_balance": str(value.current_balance),
                "available_balance": str(value.available_balance),
                "as_of": datetime.now(UTC).isoformat()}

    @staticmethod
    def _transaction_projection(value: Transaction) -> dict[str, Any]:
        return {"transaction_id": value.id, "booked_on": value.booked_on.isoformat(),
                "direction": value.direction, "amount": str(value.amount),
                "currency": value.currency, "category": value.category,
                "description": value.description, "reference": value.reference}

    @classmethod
    def _consent_projection(cls, value: AAConsent) -> dict[str, Any]:
        return {"status": value.status, "consent_id": value.consent_id,
                "purpose": value.purpose, "account_tokens": value.account_tokens,
                "information_types": value.information_types,
                "valid_from": cls._aware(value.valid_from).isoformat(),
                "valid_until": cls._aware(value.valid_until).isoformat(), "version": value.version,
                "security_flags": ["SYNTHETIC_DATA", "REVOCABLE_CONSENT"]}

    @classmethod
    def _prepared_projection(cls, value: PreparedTransfer) -> dict[str, Any]:
        return {"status": value.status, "proposed_action_id": value.proposed_action_id,
                "canonical_action_hash": value.canonical_action_hash,
                "source_account_token": value.source_account_token,
                "beneficiary_token": value.beneficiary_token, "amount": str(value.amount),
                "currency": value.currency, "rail": value.rail, "purpose": value.purpose,
                "expires_at": cls._aware(value.expires_at).isoformat(),
                "execution_available": True, "execution_tool": "bank.transfers.execute",
                "security_flags": ["SYNTHETIC_DATA", "GUARDIAN_REQUIRED"]}

    @staticmethod
    def _execution_projection(value: TransferExecution) -> dict[str, Any]:
        return {"status": value.status, "execution_id": value.execution_id,
                "proposed_action_id": value.proposed_action_id,
                "canonical_action_hash": value.canonical_action_hash,
                "amount": str(value.amount), "currency": value.currency,
                "bank_reference": value.bank_reference,
                "settled_at": value.settled_at.isoformat() if value.settled_at else None,
                "security_flags": ["SYNTHETIC_DATA", "GUARDIAN_AUTHORIZED"]}

    @staticmethod
    def _hold_projection(value: AccountHold) -> dict[str, Any]:
        return {"status": value.status, "hold_id": value.hold_id,
                "account_token": value.account_token, "amount": str(value.amount),
                "currency": value.currency, "purpose": value.purpose,
                "released_at": value.released_at.isoformat() if value.released_at else None,
                "security_flags": ["SYNTHETIC_DATA", "GUARDIAN_AUTHORIZED"]}

    @staticmethod
    def _beneficiary_change_projection(value: PreparedBeneficiaryChange) -> dict[str, Any]:
        return {"status": value.status, "change_id": value.change_id,
                "beneficiary_token": value.beneficiary_token,
                "canonical_action_hash": value.canonical_action_hash,
                "expires_at": value.expires_at.isoformat(),
                "security_flags": ["SYNTHETIC_DATA", "GUARDIAN_REQUIRED"]}

    @staticmethod
    def _reversal_projection(value: PreparedReversal) -> dict[str, Any]:
        return {"status": value.status, "reversal_id": value.reversal_id,
                "transfer_execution_id": value.transfer_execution_id,
                "amount": str(value.amount), "currency": value.currency,
                "reason": value.reason, "canonical_action_hash": value.canonical_action_hash,
                "reviewer_approval_id": value.reviewer_approval_id,
                "bank_reference": value.bank_reference,
                "security_flags": ["SYNTHETIC_DATA", "REVIEWER_AND_GUARDIAN_REQUIRED"]}

    def _receipt(self, scope: RuntimeScope, kind: str, refs: list[str]) -> str:
        body = {"call_id": scope.call_id, "kind": kind, "refs": refs}
        signature = hmac.new(get_settings().mcp_token.get_secret_value().encode(),
                             json.dumps(body, sort_keys=True, separators=(",", ":")).encode(),
                             hashlib.sha256).hexdigest()[:24]
        return f"evr_{signature}"

    @staticmethod
    def _hash(value: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                             default=str).encode()).hexdigest()

    @staticmethod
    def _audit(db: Any, scope: RuntimeScope, outcome: str, detail: dict[str, Any]) -> None:
        db.add(AuditEvent(id=str(uuid4()), tenant_id=scope.tenant_id, user_id=scope.user_id,
                          call_id=scope.call_id, tool_name=scope.canonical_name,
                          purpose=scope.purpose, outcome=outcome,
                          detail=json.dumps(detail, sort_keys=True, default=str)))

    @staticmethod
    def _event(db: Any, tenant_id: str, aggregate_type: str, aggregate_id: str,
               event_type: str, payload: dict[str, Any]) -> None:
        db.add(BankOutboxEvent(id=str(uuid4()), tenant_id=tenant_id,
                               aggregate_type=aggregate_type, aggregate_id=aggregate_id,
                               event_type=event_type, payload=payload))


bank_service = BankDemoService()
