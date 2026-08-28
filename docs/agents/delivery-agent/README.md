# Delivery Agent

## Purpose

Verify that the invoiced goods or services were fulfilled and calculate the value supported by delivery evidence.

## Inputs

- normalized purchase order, dispatch, logistics, acceptance, and delivery claims;
- signed ERP, logistics, buyer-confirmation, and evidence receipts.

## Allowed tools

- ERP fulfilment reads;
- logistics/delivery status reads;
- buyer-confirmation workflow;
- evidence consistency search.

## Output

A structured `DeliveryFinding` containing delivered quantity/value, dates, acceptance status, mismatches, and cited receipt IDs.

## Restrictions

- Cannot assume delivery from an invoice alone.
- Cannot approve financing or invoke payment/execution tools.

