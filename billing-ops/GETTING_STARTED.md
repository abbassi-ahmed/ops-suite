# Getting started — first time setup

This module runs on the **same RailCall server** as `stripe-ops` and
`twilio-ops` — no third RailCall install, just a third control panel (on
its own port) reusing the Stripe + Twilio credentials you've already set up
for the other two.

---

## Part 1 — one-time setup

Skip any step whose result already exists.

### 1. RailCall CLI + local publisher key
If you've already done this for stripe-ops/twilio-ops, skip this.
```bash
curl -fsSL https://railcall.ai/install.sh | bash
export PATH="$PATH:$HOME/.railcall/bin"
railcall market publisher init local-test
```

### 2. Sign the module
Re-run this after any edit to `module.json` or `handlers/handler.py`:
```bash
cd ~/railcall-modules/billing-ops
python3 sign_module.py
```

### 3. Deploy it into RailCall's modules folder
```bash
mkdir -p ~/.railcall/station/modules/billing-ops/handlers
cp ~/railcall-modules/billing-ops/module.json ~/.railcall/station/modules/billing-ops/module.json
cp ~/railcall-modules/billing-ops/module.sig ~/.railcall/station/modules/billing-ops/module.sig
cp ~/railcall-modules/billing-ops/handlers/handler.py ~/.railcall/station/modules/billing-ops/handlers/handler.py
```

---

## Part 2 — every time you want to use it

### Terminal 1 — the real RailCall server
Needs **all three** credentials exported — this module touches both
providers:
```bash
export PATH="$PATH:$HOME/.railcall/bin"
export STRIPE_SECRET_KEY=sk_test_...
export TWILIO_ACCOUNT_SID=AC...
export TWILIO_AUTH_TOKEN=...
python3 ~/.railcall/station/workbench/studio_server.py --no-open
```
Wait for `[modules] loaded=3 rejected=0`.

### Terminal 2 — the billing-ops control panel
```bash
cd ~/railcall-modules/billing-ops/ui
python3 server.py
```
Wait for `billing-ops control panel -> http://127.0.0.1:8902`.

(stripe-ops's panel is on `:8900`, twilio-ops's on `:8901` — all three can
run at once, each in its own terminal.)

### Browser
Open **http://127.0.0.1:8902**.

Suggested first click-through: `list_invoices_needing_reminder` (see
what's outstanding) → `preview_invoice_reminder` on one of those invoice
IDs (see the exact text) → `send_invoice_reminder_sms` with the same
inputs (send it for real).

---

## Troubleshooting

**"Address already in use"**
```bash
lsof -ti:8799 | xargs kill -9   # RailCall's own server
lsof -ti:8902 | xargs kill -9   # this panel
```

**A command fails with "STRIPE_SECRET_KEY is not set" / "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must both be set"**
Terminal 1 is missing one of the three env vars — restart it with all
three exported (Part 2 above).

**`send_invoice_reminder_sms` fails with a Twilio "Mismatch between the 'From' number..." error**
The `from` number isn't actually owned by this Twilio account. Check
Twilio Console → Phone Numbers → Manage → Active Numbers for the real one.

**A command shows up as rejected after an edit**
Re-run `python3 sign_module.py`, redeploy (step 3), then reload:
```bash
SESSION_TOKEN=$(cat ~/.railcall/station/.railcall_workspace/session_token)
curl -s -X POST http://127.0.0.1:8799/api/modules/reload \
  -H "X-RailCall-Session: $SESSION_TOKEN" -H "Content-Type: application/json" \
  -H "Origin: http://127.0.0.1:8799" -H "Referer: http://127.0.0.1:8799/v2" -d '{}'
```
