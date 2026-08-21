---
document_id: policy_payment_001
document_type: payment_policy
title: Payment Policy
version: "1.0"
effective_date: 2026-08-21
---

# Payment Policy

## Accepted Payment Methods

ShopFlow accepts the following payment methods at checkout:

- **Card** (credit/debit)
- **UPI**
- **Netbanking**
- **Cash on Delivery (COD)**
- **Wallet**

## Payment Lifecycle

Every order has exactly one associated payment, which moves through the following
states:

1. **Pending** — payment has been initiated but not yet confirmed.
2. **Authorized** — payment has been authorized by the provider but not yet captured.
3. **Paid** — payment has been successfully collected.
4. **Failed** — the payment attempt did not succeed.
5. **Refunded** — the full payment amount has been returned to the customer following
   a completed return or cancellation.
6. **Partially Refunded** — a portion of the payment has been refunded (reserved for
   future partial-refund support; not currently used).

## Failed Payments

If a payment fails, the associated order is automatically cancelled — a failed payment
means no funds were collected, so there is nothing to fulfill. The customer can place a
new order and retry with the same or a different payment method.

## Cash on Delivery

For COD orders, payment is collected by the delivery agent at the time of delivery.
The payment status remains Pending until delivery is confirmed, at which point it is
updated to Paid. COD orders that are returned before payment is collected do not
require a refund, since no payment was made.

## Payment Security

ShopFlow does not store raw card numbers or banking credentials. All payment processing
is handled through a PCI-compliant payment gateway, and only a transaction reference is
retained for record-keeping.