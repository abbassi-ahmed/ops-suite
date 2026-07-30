# Getting started — first time setup

This module runs on the **same RailCall server** as `stripe-ops` — you
don't need a second RailCall install, just a second control panel (on a
different port) and Twilio credentials in the same server process.

For what each of the 10 actions does, see `ACTIONS_GUIDE.md`.

---

## Part 1 — one-time setup

Skip any step whose result already exists.

### 1. RailCall CLI + local publisher key
If you haven't done this for stripe-ops already:
```bash
curl -fsSL https://railcall.ai/install.sh | bash
export PATH="$PATH:$HOME/.railcall/bin"
railcall market publisher init local-test
```

### 2. Sign the module
Re-run this after any edit to `module.json` or `handlers/handler.py`:
```bash
cd ~/railcall-modules/twilio-ops
python3 sign_module.py
```

### 3. Deploy it into RailCall's modules folder
```bash
mkdir -p ~/.railcall/station/modules/twilio-ops/handlers
cp ~/railcall-modules/twilio-ops/module.json ~/.railcall/station/modules/twilio-ops/module.json
cp ~/railcall-modules/twilio-ops/module.sig ~/.railcall/station/modules/twilio-ops/module.sig
cp ~/railcall-modules/twilio-ops/handlers/handler.py ~/.railcall/station/modules/twilio-ops/handlers/handler.py
```

### 4. Verify your phone number with Twilio (trial accounts only)
Trial accounts can only send to/from **verified** numbers. In the Twilio
Console: Phone Numbers → Manage → Verified Caller IDs → add your own
number and confirm it via the code Twilio sends you.

---

## Part 2 — every time you want to use it

### Terminal 1 — the real RailCall server
Set **both** Stripe and Twilio credentials here if you want both modules
usable at once (the server hosts every installed module):
```bash
export PATH="$PATH:$HOME/.railcall/bin"
export STRIPE_SECRET_KEY=sk_test_...
export TWILIO_ACCOUNT_SID=AC...
export TWILIO_AUTH_TOKEN=...
python3 ~/.railcall/station/workbench/studio_server.py --no-open
```
Wait for `[modules] loaded=2 rejected=0`.

### Terminal 2 — the Twilio control panel
```bash
cd ~/railcall-modules/twilio-ops/ui
python3 server.py
```
Wait for `twilio-ops control panel -> http://127.0.0.1:8901`.

(The Stripe panel, if you want it running too, is a separate terminal on
`~/railcall-modules/stripe-ops/ui/server.py`, port `8900`.)

### Browser
Open **http://127.0.0.1:8901**.

---

## Troubleshooting

**"Address already in use"**
```bash
lsof -ti:8799 | xargs kill -9   # RailCall's own server
lsof -ti:8901 | xargs kill -9   # this panel
```

**A Twilio command fails with a config error**
Terminal 1 doesn't have `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN` set —
restart it with both exported.

**"Twilio rejected ... trial accounts can only call verified caller IDs"**
Go verify the number in the Twilio Console (Part 1, step 4) before
retrying.

**A command shows up as rejected after an edit**
Re-run `python3 sign_module.py`, redeploy (step 3), then reload:
```bash
SESSION_TOKEN=$(cat ~/.railcall/station/.railcall_workspace/session_token)
curl -s -X POST http://127.0.0.1:8799/api/modules/reload \
  -H "X-RailCall-Session: $SESSION_TOKEN" -H "Content-Type: application/json" \
  -H "Origin: http://127.0.0.1:8799" -H "Referer: http://127.0.0.1:8799/v2" -d '{}'
```
