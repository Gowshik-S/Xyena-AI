# Guardian Agent

## Purpose

Continuously observe meaningful agent/tool activity and govern sensitive or financially consequential actions before execution.

## Inputs

- trusted identity, scope, role, and mandate;
- proposed action and canonical hash;
- signed evidence receipts and completeness/consistency result;
- tool, connector, counterparty, behaviour, exposure, simulation, and action-graph signals;
- applicable domain and tenant policies.

## Decisions

- `ALLOW`;
- `CONSTRAIN`;
- `VERIFY`;
- `BLOCK`;
- `ESCALATE`.

## Output

A reason-coded `GuardianDecision`. `ALLOW` and `CONSTRAIN` may issue a signed, short-lived, single-use authorization bound to the exact action hash.

## Restrictions

- Guardian is independent and cannot be outvoted by domain agents.
- It cannot treat model reasoning or memory as authority.
- It must fail closed for financial execution when authorization, audit, mandate, or atomic reservation cannot be verified.

