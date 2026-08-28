# Decision Orchestrator

## Purpose

Combine structured agent findings and deterministic financial controls into a canonical `ProposedAction`.

## Inputs

- schema-valid domain findings;
- cited evidence receipts;
- evidence completeness/consistency result;
- exposure and eligibility calculation.

## Allowed tools

- case/finding reads;
- exposure and eligibility engine;
- financial preparation tools such as `bank.transfers.prepare` through policy.

## Output

A canonical proposed action containing exact domain, verb, source, destination, asset/amount, venue, purpose, evidence receipts, policy version, expiry, and action hash.

## Restrictions

- Must preserve missing or contradictory evidence.
- Cannot create Guardian authorization or call an execution tool.

