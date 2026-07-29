# ops-suite — governed Stripe + Twilio + billing-reminder module for RailCall

One signed RailCall module bundling three things that were originally built
and tested as separate modules, merged into a single marketplace listing:

- **16 Stripe commands** — refunds (single + bulk), dispute responses,
  subscription cancellation (with optional refund), invoice voiding,
  PaymentIntent capture/cancel, customer/charge search and lookup,
  a customer-360 join, and a disputes-due-soon urgency view.
- **10 Twilio commands** — SMS send (single, bulk, templated), voice calls,
  message/call history and search, account usage, and phone-number release.
- **3 cross-provider billing commands** — the composite that neither Stripe
  nor Twilio can do alone: look up a real open Stripe invoice, render the
  exact SMS reminder text (amount, due date, payment link), and send it via
  Twilio. One Stripe read + one Twilio write, behind a single approval.

Every command that mutates state (a refund, a send, a cancellation) is
marked `"mode": "write_requires_approval"` in `module.json`, so RailCall's
airlock forces **preview → approve → execute** for it automatically before
anything real happens. Read-only lookups run instantly.

## Install

```bash
railcall market install abbassi-ahmed/ops-suite
```

Requires three credentials, exported wherever your RailCall Studio server
runs: `STRIPE_SECRET_KEY`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`.

## Run it locally (for development/testing, not required to just use it)

```bash
# 1. Sign (after any edit to module.json or handlers/handler.py)
python3 sign_module.py

# 2. Deploy into RailCall's modules folder
mkdir -p ~/.railcall/station/modules/ops-suite/handlers
cp module.json ~/.railcall/station/modules/ops-suite/module.json
cp module.sig  ~/.railcall/station/modules/ops-suite/module.sig
cp handlers/handler.py ~/.railcall/station/modules/ops-suite/handlers/handler.py

# 3. Start the RailCall server with all three credentials exported
export STRIPE_SECRET_KEY=sk_test_...
export TWILIO_ACCOUNT_SID=AC...
export TWILIO_AUTH_TOKEN=...
python3 ~/.railcall/station/workbench/studio_server.py --no-open
```

Wait for `[modules] loaded=... rejected=0`, then drive it through RailCall's
own command API (`/api/commands/preview`, `/api/commands/approve`,
`/api/commands/execute`) or a UI built on top of it.

See `TESTING.md` for how this exact logic was verified against real Stripe
test-mode and Twilio trial accounts before publishing.

## Where this module came from

This module is a merge of three modules that were originally built, tested,
and used independently: `stripe-ops`, `twilio-ops`, and `billing-ops` (the
last one being the cross-provider composite). They were combined into one
bundle for a single marketplace listing. The only change made during the
merge — beyond concatenation — was renaming two internal helper functions
that happened to share a name across the Stripe and Twilio sources
(`_request`, doing two different things in each) to `_stripe_ops_request`
and `_twilio_ops_request` so one didn't silently shadow the other. Every
command's actual logic is unchanged from its original, independently
tested source.

## Known limitations

- RailCall's own airlock preview only echoes back the inputs you typed for
  a write command — it doesn't call the handler ahead of time, so it can't
  show you a fetched invoice's real amount before approval.
  `preview_invoice_reminder` exists specifically to work around this for
  the billing-reminder flow: it does the same Stripe fetch + render as the
  real send, without the Twilio call, so you can see the literal text
  before sending.
- `release_phone_number` (Twilio) is irreversible and was intentionally
  never exercised for real in testing — a trial account only has one
  number to lose.
- Twilio's Messages endpoint is not idempotent — a retried send after a
  network timeout could in principle send twice.

## Tag

`contest:2026Q3`
