# stripe-ops — airlock-gated Stripe module for RailCall

## What it does

13 commands covering the Stripe operations a support/finance ops team
actually does day to day — not just single-object CRUD:

**Reads (6, instant, no approval):** `list_charges`, `get_customer`,
`list_disputes`, plus `search_charges` (filtered search — amount range,
status, customer, date window — via Stripe's Search Query Language),
`customer_360` (customer profile + recent charges + subscriptions, joined
in one call), and `list_disputes_due_soon` (disputes sorted by how soon
their response deadline is).

**Writes (7, airlock-gated):** `create_refund`, `respond_to_dispute`,
`cancel_subscription`, `capture_payment_intent`, `void_invoice`, plus two
multi-step commands that bundle several Stripe calls behind one preview —
`bulk_refund` (refund up to 25 charges in one approval, with independent
per-charge success/failure tracking) and `cancel_subscription_and_refund`
(cancels a subscription AND refunds its latest paid invoice in one step —
the real "customer wants out and their money back" request).

Every write command is flagged so RailCall's airlock forces a preview of
exactly what will happen before anyone can approve it, and every execution
gets a signed receipt. Single and bulk refunds/captures carry deterministic
Stripe idempotency keys so a retried approval can't double-fire.

## Who it's for

A support or finance ops person who currently does refunds/cancellations by
hand in the Stripe dashboard (no review step, no audit trail) or runs
scripts with no human checkpoint. This gives them a "someone has to see the
diff and approve" gate, a signed receipt for every money-moving action, and
commands that match a real ops week: a batch of duplicate charges, a
churn-and-refund request, "what needs my attention today."

## Install

```
railcall market install your-handle/stripe-ops
railcall connect your-handle/stripe-ops   # prompts for STRIPE_SECRET_KEY
```

Use a Stripe **test-mode** key (`sk_test_...`) to try it safely; a **live**
key only once you trust the flow.

## Example

Every command runs from a plain terminal — no browser required. Start
`railcall studio --no-open` with `STRIPE_SECRET_KEY` exported, then use
`railcall_term.py` (in the root of this repo) to drive the same
preview → approve → execute airlock the browser UI uses:

```
python3 railcall_term.py stripe-ops.list_charges --limit=5
# → {"charges": [{"id": "py_3N...", "amount": 4200, "currency": "usd",
#     "status": "succeeded", "customer": "cus_P8...", "created": 1719000000,
#     "refunded": false}], "has_more": true}

python3 railcall_term.py stripe-ops.create_refund --charge_id=py_3N... --reason=requested_by_customer
# → prints the exact refund about to happen
# → Approve and execute the above? [y/N] y
# → prints the signed receipt: {"refund_id": "re_1N...", "status": "succeeded",
#     "amount": 4200, "currency": "usd"}
```

## Credentials needed

One environment variable: `STRIPE_SECRET_KEY`. Get it from Stripe Dashboard
→ Developers → API keys. The key is only ever used in the request's Basic
Auth header — it is never logged, returned in output, or included in error
messages.

## Known limitations

- Charge ID prefixes vary by Stripe API version/account (`ch_`, `py_`) —
  pass whatever ID `list_charges`/`search_charges` returns for that
  account.
- `search_charges` relies on Stripe's Search API, which can lag real-time
  writes by up to ~1 minute.
- `cancel_subscription_and_refund` can't locate a refundable charge on
  accounts where invoices don't expose a direct charge reference (an
  API-version quirk) — it reports "nothing to refund" rather than guess a
  possibly-wrong charge.
- `respond_to_dispute` only supports text evidence, not file uploads.
- No pagination cursor support (`limit` capped at 100).
- No webhook support — request/response only.

## Tag

`contest:2026Q3`
