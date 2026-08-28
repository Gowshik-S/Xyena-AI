import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from .database import session
from .models import (AuditEvent, InboxEvent, JournalEntry, JournalLine, LedgerAccount,
                     OutboxEvent, PaymentInstruction, ReconciliationRecord,
                     SettlementReceipt)
from .security import LedgerSecurityError, RuntimeScope


class LedgerDomainError(RuntimeError):
    pass


class LedgerService:
    async def account_balance(self, scope: RuntimeScope, account_id: str) -> dict[str, Any]:
        async with session() as db:
            value = await self._account(db, scope.tenant_id, account_id)
            self._audit(db, scope, "SUCCESS", {"account_id": account_id})
            return self._account_projection(value)

    async def get_journal(self, scope: RuntimeScope, journal_id: str) -> dict[str, Any]:
        async with session() as db:
            value = await self._journal(db, scope.tenant_id, journal_id)
            lines = (await db.scalars(select(JournalLine).where(
                JournalLine.journal_id == journal_id))).all()
            self._audit(db, scope, "SUCCESS", {"journal_id": journal_id})
            return self._journal_projection(value, lines)

    async def payment_status(self, scope: RuntimeScope, payment_id: str) -> dict[str, Any]:
        async with session() as db:
            value = await db.scalar(select(PaymentInstruction).where(
                PaymentInstruction.payment_id == payment_id,
                PaymentInstruction.tenant_id == scope.tenant_id))
            if value is None:
                raise LedgerDomainError("Payment was not found in the signed tenant.")
            return self._payment_projection(value)

    async def reconciliation(self, scope: RuntimeScope, payment_id: str) -> dict[str, Any]:
        async with session() as db:
            value = await db.scalar(select(ReconciliationRecord).where(
                ReconciliationRecord.payment_id == payment_id,
                ReconciliationRecord.tenant_id == scope.tenant_id))
            if value is None:
                raise LedgerDomainError("Reconciliation record was not found.")
            return self._reconciliation_projection(value)

    async def prepare_disbursement(self, scope: RuntimeScope, financing_case_id: str,
                                   source_account_token: str, beneficiary_token: str,
                                   amount: str, currency: str, rail: str,
                                   client_idempotency_key: str) -> dict[str, Any]:
        value_amount = self._amount(amount)
        if currency != "INR" or rail != "DEMO_BANK_RAIL":
            raise LedgerDomainError("Only synthetic INR over DEMO_BANK_RAIL is supported.")
        action = {"tenant_id": scope.tenant_id, "financing_case_id": financing_case_id,
                  "source_account_token": source_account_token,
                  "beneficiary_token": beneficiary_token, "amount": str(value_amount),
                  "currency": currency, "rail": rail,
                  "client_idempotency_key": client_idempotency_key,
                  "purpose": scope.purpose}
        action_hash = self._hash(action)
        async with session() as db:
            existing = await db.scalar(select(JournalEntry).where(
                JournalEntry.tenant_id == scope.tenant_id,
                JournalEntry.idempotency_key == client_idempotency_key))
            if existing:
                if existing.canonical_action_hash != action_hash:
                    raise LedgerDomainError("Idempotency key is bound to another journal payload.")
                payment = await db.scalar(select(PaymentInstruction).where(
                    PaymentInstruction.journal_id == existing.journal_id))
                return await self._disbursement_projection(db, existing, payment)
            await self._account(db, scope.tenant_id, "ledger_loan_receivable")
            await self._account(db, scope.tenant_id, "ledger_cash_clearing")
            journal_id, payment_id = f"jrnl_{uuid4().hex[:18]}", f"pay_{uuid4().hex[:18]}"
            journal = JournalEntry(
                journal_id=journal_id, tenant_id=scope.tenant_id,
                financing_case_id=financing_case_id, entry_type="DISBURSEMENT",
                description=f"Synthetic financing disbursement for {financing_case_id}",
                currency=currency, total_debits=value_amount, total_credits=value_amount,
                status="VALIDATED", idempotency_key=client_idempotency_key,
                canonical_action_hash=action_hash)
            payment = PaymentInstruction(
                payment_id=payment_id, tenant_id=scope.tenant_id, journal_id=journal_id,
                financing_case_id=financing_case_id, source_account_token=source_account_token,
                beneficiary_token=beneficiary_token, amount=value_amount, currency=currency,
                rail=rail, client_idempotency_key=client_idempotency_key, status="PREPARED")
            db.add_all([journal, payment,
                JournalLine(line_id=str(uuid4()), journal_id=journal_id,
                            account_id="ledger_loan_receivable", side="DEBIT",
                            amount=value_amount, currency=currency, reference=financing_case_id),
                JournalLine(line_id=str(uuid4()), journal_id=journal_id,
                            account_id="ledger_cash_clearing", side="CREDIT",
                            amount=value_amount, currency=currency, reference=financing_case_id)])
            self._assert_balanced(journal)
            self._audit(db, scope, "PREPARED", {"journal_id": journal_id, "payment_id": payment_id})
            await db.flush()
            return await self._disbursement_projection(db, journal, payment)

    async def execute_disbursement(self, scope: RuntimeScope, journal_id: str,
                                   canonical_action_hash: str,
                                   bank_proposed_action_id: str,
                                   bank_action_hash: str,
                                   bank_execution_id: str) -> dict[str, Any]:
        async with session() as db:
            replay = await db.scalar(select(JournalEntry).where(
                JournalEntry.tenant_id == scope.tenant_id,
                JournalEntry.guardian_call_id == scope.call_id))
            if replay and replay.journal_id != journal_id:
                raise LedgerSecurityError("Guardian call id has already posted another journal.")
            journal = await self._journal(db, scope.tenant_id, journal_id)
            if journal.canonical_action_hash != canonical_action_hash:
                raise LedgerSecurityError("Canonical journal hash mismatch.")
            payment = await db.scalar(select(PaymentInstruction).where(
                PaymentInstruction.journal_id == journal_id))
            if journal.status == "POSTED":
                if (payment.bank_proposed_action_id != bank_proposed_action_id or
                        payment.bank_action_hash != bank_action_hash or
                        payment.bank_execution_id != bank_execution_id):
                    raise LedgerDomainError("Posted journal is bound to different bank execution parameters.")
                return await self._disbursement_projection(db, journal, payment)
            if journal.status != "VALIDATED":
                raise LedgerDomainError("Only a validated journal can be posted.")
            lines = (await db.scalars(select(JournalLine).where(
                JournalLine.journal_id == journal_id))).all()
            self._assert_lines_balanced(lines)
            await self._post_lines(db, scope.tenant_id, lines)
            journal.status, journal.posted_at = "POSTED", datetime.now(UTC)
            journal.guardian_call_id, journal.guardian_decision_id = scope.call_id, scope.guardian_decision_id
            payment.status = "SUBMITTED"
            payment.bank_proposed_action_id = bank_proposed_action_id
            payment.bank_action_hash = bank_action_hash
            payment.bank_execution_id = bank_execution_id
            payload = self._payment_projection(payment)
            self._event(db, scope.tenant_id, "PAYMENT", payment.payment_id,
                        "ledger.payment.submitted", payload)
            self._audit(db, scope, "POSTED", {"journal_id": journal_id, "payment_id": payment.payment_id})
            result = await self._disbursement_projection(db, journal, payment)
            result["bank_transfer_request"] = {
                "tool": "bank.transfers.execute",
                "proposed_action_id": bank_proposed_action_id,
                "canonical_action_hash": bank_action_hash,
                "execution_id": bank_execution_id,
            }
            return result

    async def prepare_reversal(self, scope: RuntimeScope, original_journal_id: str,
                               reason: str, client_idempotency_key: str) -> dict[str, Any]:
        async with session() as db:
            original = await self._journal(db, scope.tenant_id, original_journal_id)
            if original.status != "POSTED":
                raise LedgerDomainError("Only a posted journal can be reversed.")
            original_lines = (await db.scalars(select(JournalLine).where(
                JournalLine.journal_id == original_journal_id))).all()
            action = {"original_journal_id": original_journal_id, "reason": reason,
                      "idempotency_key": client_idempotency_key}
            action_hash = self._hash(action)
            existing = await db.scalar(select(JournalEntry).where(
                JournalEntry.tenant_id == scope.tenant_id,
                JournalEntry.idempotency_key == client_idempotency_key))
            if existing:
                if existing.canonical_action_hash != action_hash:
                    raise LedgerDomainError("Reversal idempotency parameter drift detected.")
                lines = (await db.scalars(select(JournalLine).where(
                    JournalLine.journal_id == existing.journal_id))).all()
                return self._journal_projection(existing, lines)
            journal_id = f"jrnl_rev_{uuid4().hex[:14]}"
            reversal = JournalEntry(
                journal_id=journal_id, tenant_id=scope.tenant_id,
                financing_case_id=original.financing_case_id, entry_type="REVERSAL",
                description=reason, currency=original.currency,
                total_debits=original.total_credits, total_credits=original.total_debits,
                status="REVIEW_REQUIRED", idempotency_key=client_idempotency_key,
                canonical_action_hash=action_hash, reversal_of_journal_id=original_journal_id)
            lines = [JournalLine(
                line_id=str(uuid4()), journal_id=journal_id, account_id=line.account_id,
                side="CREDIT" if line.side == "DEBIT" else "DEBIT", amount=line.amount,
                currency=line.currency, reference=original_journal_id) for line in original_lines]
            db.add_all([reversal, *lines])
            self._assert_lines_balanced(lines)
            self._audit(db, scope, "PREPARED", {"journal_id": journal_id})
            return self._journal_projection(reversal, lines)

    async def execute_reversal(self, scope: RuntimeScope, journal_id: str,
                               canonical_action_hash: str, reviewer_approval_id: str,
                               ) -> dict[str, Any]:
        if not reviewer_approval_id.strip():
            raise LedgerSecurityError("Reviewer approval is mandatory for a reversal.")
        async with session() as db:
            journal = await self._journal(db, scope.tenant_id, journal_id)
            if journal.canonical_action_hash != canonical_action_hash:
                raise LedgerSecurityError("Reversal canonical hash mismatch.")
            lines = (await db.scalars(select(JournalLine).where(
                JournalLine.journal_id == journal_id))).all()
            if journal.status == "POSTED":
                return self._journal_projection(journal, lines)
            if journal.status != "REVIEW_REQUIRED":
                raise LedgerDomainError("Reversal is not ready for dual approval.")
            self._assert_lines_balanced(lines)
            await self._post_lines(db, scope.tenant_id, lines)
            journal.status, journal.posted_at = "POSTED", datetime.now(UTC)
            journal.guardian_call_id, journal.guardian_decision_id = scope.call_id, scope.guardian_decision_id
            journal.reviewer_approval_id = reviewer_approval_id
            self._event(db, scope.tenant_id, "JOURNAL", journal_id,
                        "ledger.reversal.posted", {"journal_id": journal_id})
            self._audit(db, scope, "POSTED", {"journal_id": journal_id})
            return self._journal_projection(journal, lines)

    async def accept_bank_settlement(self, tenant_id: str, event_id: str,
                                     payment_id: str, bank_execution_id: str,
                                     bank_reference: str, amount: str, currency: str,
                                     settled_at: datetime) -> dict[str, Any]:
        value_amount = self._amount(amount)
        if len(bank_reference) != 10:
            raise LedgerDomainError("Bank reference must contain exactly 10 characters.")
        payload = {"payment_id": payment_id, "bank_execution_id": bank_execution_id,
                   "bank_reference": bank_reference, "amount": str(value_amount),
                   "currency": currency, "settled_at": settled_at.isoformat()}
        payload_hash = self._hash(payload)
        async with session() as db:
            inbox = await db.get(InboxEvent, event_id)
            if inbox:
                if inbox.payload_hash != payload_hash:
                    raise LedgerSecurityError("Settlement event id parameter drift detected.")
                reconciliation = await db.scalar(select(ReconciliationRecord).where(
                    ReconciliationRecord.payment_id == payment_id))
                return self._reconciliation_projection(reconciliation)
            payment = await db.scalar(select(PaymentInstruction).where(
                PaymentInstruction.payment_id == payment_id,
                PaymentInstruction.tenant_id == tenant_id))
            if payment is None or payment.bank_execution_id != bank_execution_id:
                raise LedgerDomainError("Settlement does not match the submitted payment.")
            if payment.amount != value_amount or payment.currency != currency:
                raise LedgerDomainError("Settlement amount or currency differs from payment.")
            receipt = SettlementReceipt(
                receipt_id=f"stl_{uuid4().hex[:18]}", tenant_id=tenant_id,
                payment_id=payment_id, bank_execution_id=bank_execution_id,
                bank_reference=bank_reference, amount=value_amount, currency=currency,
                settled_at=settled_at, evidence_hash=payload_hash)
            reconciliation = ReconciliationRecord(
                reconciliation_id=f"rec_{uuid4().hex[:18]}", tenant_id=tenant_id,
                payment_id=payment_id, journal_id=payment.journal_id,
                settlement_receipt_id=receipt.receipt_id, status="MATCHED",
                variance_amount=Decimal("0.00"), reconciled_at=datetime.now(UTC))
            payment.status, payment.bank_reference = "SETTLED", bank_reference
            db.add_all([receipt, reconciliation,
                        InboxEvent(event_id=event_id, tenant_id=tenant_id,
                                   event_type="bank.transfer.settled", payload_hash=payload_hash)])
            self._event(db, tenant_id, "PAYMENT", payment_id,
                        "ledger.payment.reconciled", self._reconciliation_projection(reconciliation))
            return self._reconciliation_projection(reconciliation)

    @staticmethod
    async def _account(db: Any, tenant_id: str, account_id: str) -> LedgerAccount:
        value = await db.scalar(select(LedgerAccount).where(
            LedgerAccount.account_id == account_id, LedgerAccount.tenant_id == tenant_id,
            LedgerAccount.status == "ACTIVE"))
        if value is None:
            raise LedgerDomainError("Ledger account was not found in the tenant.")
        return value

    @staticmethod
    async def _journal(db: Any, tenant_id: str, journal_id: str) -> JournalEntry:
        value = await db.scalar(select(JournalEntry).where(
            JournalEntry.journal_id == journal_id, JournalEntry.tenant_id == tenant_id))
        if value is None:
            raise LedgerDomainError("Journal was not found in the tenant.")
        return value

    async def _post_lines(self, db: Any, tenant_id: str, lines: list[JournalLine]) -> None:
        for line in lines:
            account = await self._account(db, tenant_id, line.account_id)
            account.balance += line.amount if line.side == account.normal_side else -line.amount
            account.version += 1

    @staticmethod
    def _assert_balanced(journal: JournalEntry) -> None:
        if journal.total_debits != journal.total_credits or journal.total_debits <= 0:
            raise LedgerDomainError("Journal debits and credits must be equal and positive.")

    @staticmethod
    def _assert_lines_balanced(lines: list[JournalLine]) -> None:
        debits = sum((line.amount for line in lines if line.side == "DEBIT"), Decimal("0"))
        credits = sum((line.amount for line in lines if line.side == "CREDIT"), Decimal("0"))
        if debits != credits or debits <= 0:
            raise LedgerDomainError("Journal lines violate the double-entry invariant.")

    async def _disbursement_projection(self, db: Any, journal: JournalEntry,
                                       payment: PaymentInstruction) -> dict[str, Any]:
        lines = (await db.scalars(select(JournalLine).where(
            JournalLine.journal_id == journal.journal_id))).all()
        return {"status": journal.status, "journal": self._journal_projection(journal, lines),
                "payment": self._payment_projection(payment),
                "execution_boundary": "GUARDIAN_AUTHORIZED_MCP_ONLY",
                "security_flags": ["SYNTHETIC_DATA", "DOUBLE_ENTRY_BALANCED"]}

    @staticmethod
    def _account_projection(value: LedgerAccount) -> dict[str, Any]:
        return {"account_id": value.account_id, "code": value.code, "name": value.name,
                "account_type": value.account_type, "normal_side": value.normal_side,
                "currency": value.currency, "balance": str(value.balance),
                "status": value.status, "version": value.version}

    @staticmethod
    def _journal_projection(value: JournalEntry, lines: list[JournalLine]) -> dict[str, Any]:
        return {"journal_id": value.journal_id, "financing_case_id": value.financing_case_id,
                "entry_type": value.entry_type, "description": value.description,
                "currency": value.currency, "total_debits": str(value.total_debits),
                "total_credits": str(value.total_credits), "status": value.status,
                "canonical_action_hash": value.canonical_action_hash,
                "reversal_of_journal_id": value.reversal_of_journal_id,
                "posted_at": value.posted_at.isoformat() if value.posted_at else None,
                "lines": [{"line_id": line.line_id, "account_id": line.account_id,
                           "side": line.side, "amount": str(line.amount),
                           "currency": line.currency, "reference": line.reference} for line in lines]}

    @staticmethod
    def _payment_projection(value: PaymentInstruction) -> dict[str, Any]:
        return {"payment_id": value.payment_id, "journal_id": value.journal_id,
                "financing_case_id": value.financing_case_id,
                "source_account_token": value.source_account_token,
                "beneficiary_token": value.beneficiary_token,
                "amount": str(value.amount), "currency": value.currency,
                "rail": value.rail, "status": value.status,
                "bank_proposed_action_id": value.bank_proposed_action_id,
                "bank_execution_id": value.bank_execution_id,
                "bank_reference": value.bank_reference}

    @staticmethod
    def _reconciliation_projection(value: ReconciliationRecord) -> dict[str, Any]:
        return {"reconciliation_id": value.reconciliation_id,
                "payment_id": value.payment_id, "journal_id": value.journal_id,
                "settlement_receipt_id": value.settlement_receipt_id,
                "status": value.status, "variance_amount": str(value.variance_amount),
                "reason": value.reason,
                "reconciled_at": value.reconciled_at.isoformat() if value.reconciled_at else None}

    @staticmethod
    def _amount(value: str) -> Decimal:
        try:
            amount = Decimal(value).quantize(Decimal("0.01"))
        except InvalidOperation as exc:
            raise LedgerDomainError("Amount must be a decimal value.") from exc
        if not amount.is_finite() or amount <= 0:
            raise LedgerDomainError("Amount must be greater than zero.")
        return amount

    @staticmethod
    def _hash(value: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                             default=str).encode()).hexdigest()

    @staticmethod
    def _audit(db: Any, scope: RuntimeScope, outcome: str, detail: dict[str, Any]) -> None:
        db.add(AuditEvent(id=str(uuid4()), tenant_id=scope.tenant_id, user_id=scope.user_id,
                          call_id=scope.call_id, tool_name=scope.canonical_name,
                          outcome=outcome, detail=json.dumps(detail, sort_keys=True)))

    @staticmethod
    def _event(db: Any, tenant_id: str, aggregate_type: str, aggregate_id: str,
               event_type: str, payload: dict[str, Any]) -> None:
        db.add(OutboxEvent(id=str(uuid4()), tenant_id=tenant_id,
                           aggregate_type=aggregate_type, aggregate_id=aggregate_id,
                           event_type=event_type, payload=payload))


ledger_service = LedgerService()
