"""Governed synthetic disbursement coordinator.

The coordinator never bypasses Guardian. When an ALWAYS-approval tool blocks, it writes the
call/correlation IDs to the checkpoint and exits. After approval, rerun with ``resume``.
"""
import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

STATE = Path(os.getenv("XYENA_E2E_STATE", ".xyena-e2e-state.json"))


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be configured")
    return value


class Coordinator:
    def __init__(self) -> None:
        self.gateway = required("XYENA_MCP_GATEWAY_URL").rstrip("/")
        self.service_token = required("XYENA_SERVICE_TOKEN")
        self.ledger_url = required("LEDGER_DEMO_URL").rstrip("/")
        self.settlement_token = required("LEDGER_DEMO_SETTLEMENT_EVENT_TOKEN")
        self.tenant_id = os.getenv("XYENA_E2E_TENANT_ID", "00000000-0000-4000-8000-000000000101")
        self.organization_id = os.getenv("XYENA_E2E_ORGANIZATION_ID", "00000000-0000-4000-8000-000000000301")
        self.user_id = os.getenv("XYENA_E2E_USER_ID", "00000000-0000-4000-8000-000000000201")

    def context(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"tenant_id": self.tenant_id, "organization_id": self.organization_id,
                "user_id": self.user_id, "session_id": state["session_id"],
                "run_id": state["run_id"], "correlation_id": state["correlation_id"],
                "roles": ["finance-operator"], "consent_ids": [],
                "policy_bundle_version": "platform-default", "locale": "en-IN",
                "timezone": "Asia/Kolkata"}

    async def call(self, state: dict[str, Any], name: str, arguments: dict[str, Any],
                   idempotency_key: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(f"{self.gateway}/internal/mcp/calls",
                headers={"Authorization": f"Bearer {self.service_token}"},
                json={"run_id": state["run_id"], "agent_name": "xyena-supervisor",
                      "context": self.context(state),
                      "intent": {"requested_name": name, "arguments": arguments,
                                 "purpose": state["purpose"],
                                 "resource_refs": [state["financing_case_id"]],
                                 "idempotency_key": idempotency_key}})
            response.raise_for_status()
            return response.json()

    async def resume_call(self, state: dict[str, Any], pending: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(f"{self.gateway}/internal/mcp/calls/resume",
                headers={"Authorization": f"Bearer {self.service_token}"},
                json={"tenant_id": self.tenant_id, "call_id": pending["call_id"],
                      "correlation_id": state["correlation_id"]})
            response.raise_for_status()
            return response.json()

    @staticmethod
    def projection(result: dict[str, Any]) -> dict[str, Any]:
        if result.get("status") != "SUCCEEDED" or not isinstance(result.get("model_projection"), dict):
            raise RuntimeError(f"Tool did not succeed: {result}")
        return result["model_projection"]

    async def start(self) -> dict[str, Any]:
        state = {"version": 1, "stage": "PREPARING", "run_id": required("XYENA_E2E_RUN_ID"),
                 "session_id": required("XYENA_E2E_SESSION_ID"),
                 "correlation_id": str(uuid4()), "financing_case_id": "case_demo_e2e_001",
                 "purpose": "synthetic financing disbursement",
                 "bank_execution_id": f"exec_{uuid4().hex[:18]}"}
        bank = self.projection(await self.call(state, "bank.transfers.prepare",
            {"source_account_token": "acct_demo_operating",
             "beneficiary_token": "ben_demo_verified", "amount": "125000.00",
             "currency": "INR", "rail": "DEMO_BANK_RAIL",
             "client_idempotency_key": "e2e-bank-case-demo-001"}, "e2e-bank-case-demo-001"))
        ledger = self.projection(await self.call(state, "ledger.disbursements.prepare",
            {"financing_case_id": state["financing_case_id"],
             "source_account_token": "acct_demo_operating",
             "beneficiary_token": "ben_demo_verified", "amount": "125000.00",
             "currency": "INR", "rail": "DEMO_BANK_RAIL",
             "client_idempotency_key": "e2e-ledger-case-demo-001"}, "e2e-ledger-case-demo-001"))
        state["bank_preparation"], state["ledger_preparation"] = bank, ledger
        result = await self.call(state, "ledger.disbursements.execute",
            {"journal_id": ledger["journal"]["journal_id"],
             "canonical_action_hash": ledger["journal"]["canonical_action_hash"],
             "bank_proposed_action_id": bank["proposed_action_id"],
             "bank_action_hash": bank["canonical_action_hash"],
             "bank_execution_id": state["bank_execution_id"]}, "e2e-ledger-execute-demo-001")
        return await self._handle_ledger_result(state, result)

    async def _handle_ledger_result(self, state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        if result.get("status") == "BLOCKED":
            state.update(stage="WAITING_LEDGER_APPROVAL",
                         pending={"kind": "ledger", "call_id": result["call_id"]})
            return state
        state["ledger_execution"] = self.projection(result)
        bank = state["bank_preparation"]
        result = await self.call(state, "bank.transfers.execute",
            {"proposed_action_id": bank["proposed_action_id"],
             "canonical_action_hash": bank["canonical_action_hash"],
             "execution_id": state["bank_execution_id"]}, "e2e-bank-execute-demo-001")
        if result.get("status") == "BLOCKED":
            state.update(stage="WAITING_BANK_APPROVAL",
                         pending={"kind": "bank", "call_id": result["call_id"]})
            return state
        return await self._settle(state, self.projection(result))

    async def resume(self, state: dict[str, Any]) -> dict[str, Any]:
        result = await self.resume_call(state, state["pending"])
        if result.get("status") == "BLOCKED":
            return state
        if state["pending"]["kind"] == "ledger":
            state.pop("pending", None)
            return await self._handle_ledger_result(state, result)
        state.pop("pending", None)
        return await self._settle(state, self.projection(result))

    async def _settle(self, state: dict[str, Any], bank: dict[str, Any]) -> dict[str, Any]:
        state["bank_execution"] = bank
        payment = state["ledger_preparation"]["payment"]
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self.ledger_url}/internal/v1/bank-settlements",
                headers={"X-Settlement-Token": self.settlement_token},
                json={"event_id": f"bank-settlement-{state['bank_execution_id']}",
                      "tenant_id": self.tenant_id, "payment_id": payment["payment_id"],
                      "bank_execution_id": state["bank_execution_id"],
                      "bank_reference": bank["bank_reference"], "amount": bank["amount"],
                      "currency": bank["currency"],
                      "settled_at": bank.get("settled_at") or datetime.now(UTC).isoformat()})
            response.raise_for_status()
            state["reconciliation"] = response.json()
        state["stage"] = "RECONCILED"
        state["completed_at"] = datetime.now(UTC).isoformat()
        return state


async def main() -> None:
    args = argparse.ArgumentParser()
    args.add_argument("command", choices=["start", "resume"])
    command = args.parse_args().command
    coordinator = Coordinator()
    if command == "start":
        state = await coordinator.start()
    else:
        state = json.loads(STATE.read_text(encoding="utf-8"))
        state = await coordinator.resume(state)
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(json.dumps({"stage": state["stage"], "checkpoint": str(STATE)}, indent=2))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
