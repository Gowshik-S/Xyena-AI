# Business Agent

## Purpose

Verify business identity, registration, ownership consistency, operating status, and product eligibility.

## Inputs

- normalized business claims;
- signed registry, GST, bank-ownership, and Account Aggregator evidence receipts;
- tenant and case policy.

## Allowed tools

- business/GST registry reads;
- `bank.accounts.get`;
- `bank.beneficiaries.verify`;
- approved KYC/KYB and ownership-graph reads.

## Output

A structured `BusinessFinding` with status, confidence, cited receipt IDs, mismatches, missing evidence, and security flags.

## Restrictions

- A submitted certificate or JSON field cannot establish trusted identity by itself.
- Cannot call transfer, beneficiary-change, credit-decision, or execution tools.

