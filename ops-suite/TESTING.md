# Testing — how this was actually verified

This module's logic was tested with real, live API calls against a Stripe
test-mode account and a Twilio trial account — not a mocked or simulated
test suite. Below is what was concretely verified, split by what was
tested before the three source modules were merged, and what was
re-verified on the merged bundle itself.

## Before the merge (on the original stripe-ops / twilio-ops / billing-ops)

**Stripe — real executions confirmed:**
- Single and bulk refunds, returning real `refund_id`s and `status:
  "succeeded"`.
- A refund correctly rejected by Stripe on an uncaptured charge, with the
  handler surfacing Stripe's real error and the correct next action
  (cancel the PaymentIntent instead) rather than a generic failure.
- A refund correctly rejected on a charged-back (disputed) charge, again
  surfacing Stripe's real reason.
- `cancel_payment_intent` executed for real on a genuinely uncaptured
  PaymentIntent, confirmed via a follow-up lookup showing
  `status: "canceled"`.
- `search_customers` (by name) correctly resolving a real customer's
  `cus_...` ID with no prior knowledge of it.
- `customer_360`, `search_charges`, `list_disputes_due_soon`, and
  `list_charges` all confirmed against real seeded Stripe test data
  (customers, charges, invoices created via the real Stripe API).

**Twilio — real executions confirmed:**
- `send_sms` sent a real SMS via a verified trial-account number,
  returning a real `message_sid` and delivery status.
- Correctly rejected sends to unverified numbers and reported Twilio's own
  "verified caller ID" error honestly instead of masking it.
- `account_usage`, `list_messages`, `list_calls` confirmed against a real
  Twilio trial account.

**Cross-provider (billing-ops) — real executions confirmed:**
- `list_invoices_needing_reminder` against real open Stripe invoices,
  sorted by urgency.
- `preview_invoice_reminder` rendering the exact SMS text — real amount,
  real due date, real Stripe-hosted payment link — without sending
  anything (confirmed nothing was sent by checking Twilio message history
  before/after).
- `send_invoice_reminder_sms` executed for real: one Stripe invoice fetch
  + one Twilio send, in a single approved action, confirmed via the
  receipt's `message_sid` and the real message showing up in Twilio's
  message history.
- Guards confirmed working: a reminder attempt on an already-`paid`,
  `void`, or still-`draft` invoice fails honestly with a specific reason
  instead of sending a wrong or confusing message.

**A real bug found and fixed during this testing (documented for
transparency):** handler functions must return a `(dict, None)` tuple, not
a bare dict — `studio_server.py` unpacks two values from every handler's
return, and a bare dict would have Python silently iterate its first two
*keys* as if they were the two return values, discarding all real data
without raising an error. Every handler in this module explicitly returns
`(result_dict, None)`.

## After the merge (on this exact ops-suite bundle)

The three sources above were merged into this single `handler.py`. The
only functional change made during the merge was renaming two internal
helper functions that collided by name across the Stripe and Twilio
sources (both were called `_request`, doing different things) to
`_stripe_ops_request` and `_twilio_ops_request` — everything else is
byte-identical logic to the already-tested sources.

To confirm the merge didn't break anything, this exact `ops-suite` bundle
was deployed locally and, after RailCall's loader registered all 29
commands with zero rejections, one real command from each of the three
original sources was executed through it directly:

| Command | Source | Result |
|---|---|---|
| `list_charges` | Stripe | `executed` — real charge data returned |
| `account_usage` | Twilio | `executed` — real balance/usage returned |
| `list_invoices_needing_reminder` | Billing (cross-provider) | `executed` — real open invoices returned |

## What was intentionally not tested

- `release_phone_number` (Twilio) — deliberately never executed for real.
  It's irreversible, and the trial account this was built against only
  has one phone number to lose. This is a disclosed limitation, not an
  oversight.
- No automated/checked-in test suite exists for this module — all of the
  above was verified through direct, live API calls during development,
  not a `pytest` suite. If you're evaluating this module, the receipts
  produced by RailCall's own airlock (signed, tamper-evident, containing
  the real Stripe/Twilio response data) are the actual evidence trail for
  every execution described above.
