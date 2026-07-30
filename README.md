# RailCall modules — Stripe, Twilio, and a cross-provider billing composite

Signed RailCall marketplace modules. Every command works two ways with no
extra setup: natively in RailCall's own Studio (**Sends** → **Fire**), or
from a plain terminal via the included `railcall_term.py` client — no
custom UI required for either.

## What's here

- **[`ops-suite/`](ops-suite/)** — the published listing
  (`abbassi-ahmed/ops-suite`): all 29 commands below, bundled into one
  signed module.
- **[`stripe-ops/`](stripe-ops/)** — 13 Stripe commands (refunds, disputes,
  subscriptions, invoices, PaymentIntents).
- **[`twilio-ops/`](twilio-ops/)** — 10 Twilio commands (SMS, voice, message/
  call history, phone-number release).
- **[`billing-ops/`](billing-ops/)** — 3 cross-provider commands: look up a
  real open Stripe invoice, render the exact SMS reminder text, and send it
  via Twilio, behind a single approval.

Each module directory has its own README with the full command list,
install steps, and known limitations.

## Two ways to run any command

Every command in every module here goes through RailCall's airlock
(`preview → approve → execute`) and ends in a signed receipt, regardless
of which of these you use:

```bash
# Start RailCall Studio with the credentials the module you're using needs
export STRIPE_SECRET_KEY=sk_test_...
export TWILIO_ACCOUNT_SID=AC...
export TWILIO_AUTH_TOKEN=...
railcall studio --no-open
```

**1. RailCall's own Studio** — open `railcall studio`, go to **Sends**,
find the command (e.g. `list_charges`, `create_refund`), and click
**Fire**. This is Studio's own built-in flow; nothing extra to install.

**2. A plain terminal**, via `railcall_term.py` (in this repo's root) —
approval accepts a `terminal_confirm` method as a first-class peer to a
UI click, so the whole cycle runs without a browser at all:

```bash
python3 railcall_term.py ops-suite.list_charges --limit=5
python3 railcall_term.py ops-suite.create_refund --charge_id=py_3N... --reason=requested_by_customer
# → shows the exact payload, prompts: Approve and execute the above? [y/N]
# → on y: real execution + a signed receipt
```

`railcall_term.py` is a small, dependency-free client, not specific to
any one module — it works against any deployed module by
`<module>.<command>`, reading each command's input schema from that
module's own `module.json` so numeric fields are sent as numbers, not
strings.

## Tag

`contest:2026Q3`
