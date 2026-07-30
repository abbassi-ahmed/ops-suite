# billing-ops — cross-provider composite for RailCall

## What it does

3 commands that turn "find who owes us money and nudge them" into one
governed action instead of a manual hop between the Stripe dashboard and a
texting tool:

**Reads (2, instant, no approval):** `list_invoices_needing_reminder`
(open Stripe invoices due within N days or already overdue, soonest/most
overdue first) and `preview_invoice_reminder` (fetches one real invoice and
renders the exact SMS text — amount, due date, payment link — without
sending anything).

**Write (1, airlock-gated, two providers behind one approval):**
`send_invoice_reminder_sms` — looks up the real Stripe invoice, renders the
reminder, and sends it via Twilio SMS. One Stripe call + one Twilio call,
one signed receipt.

This isn't a second copy of stripe-ops or twilio-ops — it's what neither of
those can do alone: an action that spans both providers in a single
approved step.

## Who it's for

Whoever's already chasing overdue invoices by hand: pulling the amount from
Stripe, writing a text, sending it from a phone or a separate tool, with no
record of what was actually sent or approved. This makes the whole
lookup → draft → send sequence one governed, receipted action.

## Run it locally

This is how to actually run the module today, end to end. (`GETTING_STARTED.md`
has the same steps with more troubleshooting.)

**Prerequisites**
- The RailCall CLI installed (`~/.railcall/…`) with a local publisher key
  (`railcall market publisher init local-test`).
- Python 3 with `requests` available to RailCall's interpreter
  (`python3 -m pip install --user --break-system-packages requests`).
- A **Stripe test** secret key (`sk_test_…`) and **Twilio trial** credentials
  (Account SID `AC…`, Auth Token), plus a Twilio number to send from. On a
  trial account, verify the recipient number as a Caller ID first.

**1. Sign the module** (re-run after any edit to `module.json` or `handlers/handler.py`):
```bash
cd path/to/billing-ops
python3 sign_module.py
```

**2. Deploy it into RailCall's modules folder:**
```bash
mkdir -p ~/.railcall/station/modules/billing-ops/handlers
cp module.json  ~/.railcall/station/modules/billing-ops/module.json
cp module.sig   ~/.railcall/station/modules/billing-ops/module.sig
cp handlers/handler.py ~/.railcall/station/modules/billing-ops/handlers/handler.py
```

**3. Start RailCall Studio** with all three credentials exported (this
module touches both providers):
```bash
export STRIPE_SECRET_KEY=sk_test_...
export TWILIO_ACCOUNT_SID=AC...
export TWILIO_AUTH_TOKEN=...
railcall studio --no-open
```
Wait for `[modules] loaded=... rejected=0`.

**4. Run every command from a plain terminal** — no browser required.
`railcall_term.py` (in the root of this repo) drives the same
preview → approve → execute airlock the browser UI uses, with approval
bound via `terminal_confirm` instead of a UI click:
```bash
python3 railcall_term.py billing-ops.list_invoices_needing_reminder --within_days=7
python3 railcall_term.py billing-ops.preview_invoice_reminder --invoice_id=in_1abc... --to=+15551234567
python3 railcall_term.py billing-ops.send_invoice_reminder_sms --invoice_id=in_1abc... --to=+15551234567 --from=+15557654321
# → prints the exact reminder text about to be sent
# → Approve and execute the above? [y/N] y
# → prints the signed receipt with message_sid and message_status
```

> **Marketplace install (not yet available):** the eventual published flow is
> `railcall market install your-handle/billing-ops`, but this module has not
> been published yet — use the local deploy above. It reuses the same Stripe
> and Twilio credentials as `stripe-ops`/`twilio-ops`, not separate ones.

## What each command takes and returns

You run these from a terminal (step 4 above); here's the shape of each
command's inputs and output:

```
python3 railcall_term.py billing-ops.list_invoices_needing_reminder --within_days=7
# → {"invoices_needing_reminder": [{"invoice_id": "in_1abc...",
#     "customer_name": "Alex Chen", "amount_due": 4900, "currency": "usd",
#     "due_date": 1785200000, "hosted_invoice_url": "https://invoice.stripe.com/..."}]}

python3 railcall_term.py billing-ops.preview_invoice_reminder \
  --invoice_id=in_1abc... --to=+15551234567
# → rendered_message: "Hi Alex Chen, this is a reminder that your invoice
#     for 49.00 USD is due Aug 03, 2026. Pay here: https://invoice.stripe.com/..."
#   nothing sent yet

python3 railcall_term.py billing-ops.send_invoice_reminder_sms \
  --invoice_id=in_1abc... --to=+15551234567 --from=+15557654321
# → terminal preview shows invoice_id/to/from/custom_note as typed
#   (see "Known limitations" — it can't show the fetched amount yet)
# → Approve and execute the above? [y/N] y
# → real Stripe fetch + real Twilio send, then a receipt with
#   the rendered message, message_sid, and message_status
```

## Credentials needed

The same three environment variables `stripe-ops` and `twilio-ops` already
use: `STRIPE_SECRET_KEY`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`. No new
secrets to manage — this module is additive on top of accounts you've
already connected.

## Known limitations

- **RailCall's built-in airlock preview can't show the real invoice amount
  before approval** — it only ever echoes back the raw inputs you typed
  (confirmed by reading `studio_server.py`'s `preview_command()`), not the
  result of calling a handler. That's a platform behavior, not a bug in
  this module. `preview_invoice_reminder` exists specifically to work
  around it: it runs the exact same Stripe fetch + render as the real send,
  just without the Twilio call, so you can see the literal words first.
- An invoice with no `due_date` set is excluded from
  `list_invoices_needing_reminder` (a "due within N days" window doesn't
  apply to it), but `preview_invoice_reminder`/`send_invoice_reminder_sms`
  still work fine on it directly by `invoice_id` — the message just omits
  the due-date clause.
- Guards against sending a reminder for an invoice that's already `paid`,
  `void`, `uncollectible`, or still a `draft` — fails honestly with a clear
  reason instead of sending a wrong or confusing message.
- Twilio's Messages endpoint is not idempotent (same disclosed limitation
  as `twilio-ops`) — a retried send after a timeout could send twice.

## Tag

`contest:2026Q3`
