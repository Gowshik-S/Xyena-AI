# Monitoring Agent

## Purpose

Reconcile execution outcomes and continuously update exposure, behaviour posture, connector health, and action-chain risk.

## Inputs

- execution receipts and status lookups;
- Guardian decisions and authorization consumption events;
- Bank/Wallet/Portfolio/DeFi MCP telemetry;
- exposure reservations and workflow state.

## Allowed tools

- execution-status and reconciliation reads;
- event/outbox and audit reads;
- exposure update under deterministic policy;
- incident/escalation workflow tools.

## Output

A structured `MonitoringFinding` containing final state, reconciliation status, exposure change, anomalies, cascade signals, and recommended posture changes.

## Restrictions

- Cannot blindly retry an unknown financial outcome.
- Cannot rewrite historical evidence or audit records.
- Corrective financial actions require a new proposal and Guardian authorization.

