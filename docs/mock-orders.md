# Mock Orders — Aura Skincare

## Purpose

This document defines the fictional sample orders used for development, testing, and demonstration of the Aura Skincare AI voice-support agent.

All customer names, order IDs, and tracking numbers below are assessment fixtures, not real customer data.

## Order List

### ORD-101 — Priya Sharma

| Field | Value |
|---|---|
| Order ID | `ORD-101` |
| Customer | Priya Sharma |
| Items | Vitamin C Serum (30ml) |
| Total | ₹699 |
| Status | Out for Delivery |
| Carrier | BlueDart |
| Tracking Number | `BD-982103` |
| Expected Delivery | Today by 6 PM |

### ORD-102 — Rahul Verma

| Field | Value |
|---|---|
| Order ID | `ORD-102` |
| Customer | Rahul Verma |
| Items | Hydrating Sunscreen SPF 50 |
| Total | ₹499 |
| Status | Delivered |
| Carrier | Delhivery |
| Tracking Number | `DL-441029` |
| Delivery Date | 14 days ago |

### ORD-103 — Ananya Patel

| Field | Value |
|---|---|
| Order ID | `ORD-103` |
| Customer | Ananya Patel |
| Items | Green Tea Face Wash; Green Tea Toner |
| Total | ₹850 |
| Status | Processing |
| Carrier | Not yet assigned |
| Tracking Number | Not yet assigned |
| Order Age | 3 hours |

## Implementation Notes

- These records are static mock data for the assessment.
- Order lookup must handle unknown order IDs gracefully.
- The backend is the source of truth for order status and action eligibility.
- `ORD-103` is initially eligible for cancellation because its status is `Processing`. The backend must re-check its current status before executing a cancellation.
- `ORD-101` cannot be cancelled under the assessment's cancellation policy because it is already `Out for Delivery`.
- `ORD-102` was delivered 14 days ago, outside the standard 7-day return window.
- Do not infer missing information or promise outcomes that are not supported by the order data and documented brand policies.
- If an action changes an order, update the mock data consistently for subsequent lookups during that application session.

## Related Documentation

- `docs/functional-requirements.md` — application behaviour and acceptance criteria.
- `docs/order-action-tools.md` — order creation, cancellation, and action safeguards.
- Brand shipping, return, damage-reporting, and cancellation rules should be documented in the functional requirements, not duplicated here.
