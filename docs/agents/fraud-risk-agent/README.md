# Fraud and Risk Agent

## Purpose

Detect suspicious documents, counterparties, behaviour, duplicates, collusion, circular activity, compromised sources, and dangerous action chains.

## Inputs

- all structured domain findings and receipt metadata;
- provenance, counterparty, tool-call, and action graphs;
- historical behaviour baselines and security flags.

## Allowed tools

- scoped fraud and graph search;
- counterparty and destination intelligence;
- connector health and provenance reads;
- approved sanctions/KYB risk reads.

## Output

A structured `RiskFinding` with signals, affected entities, graph references, severity, confidence, and recommended controls.

## Restrictions

- An anomaly is a risk signal, not automatic proof of fraud.
- Cannot authorize, block, or execute financial actions; Guardian owns the final governance verdict.

