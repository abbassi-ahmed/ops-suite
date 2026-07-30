# Getting started — first time setup

This is the "how do I actually run this" guide. If this is your first time,
follow **Part 1** once, then **Part 2** every time you want to use it.

For what each of the 13 actions actually does, see `ACTIONS_GUIDE.md`.
For the official contest-facing description, see `README.md`.

---

## Part 1 — one-time setup

Do this once. If you've already done it before (files already exist), skip
straight to Part 2.

### 1. Install the RailCall CLI

```bash
curl -fsSL https://railcall.ai/install.sh | bash
```

Verify it worked:
```bash
export PATH="$PATH:$HOME/.railcall/bin"
railcall version
```

### 2. Mint a local publisher key (one time, no account needed)

This is just a local signing key on your machine — it does **not** require
logging in or creating a RailCall account.

```bash
railcall market publisher init local-test
```

Skip this if `~/.railcall/marketplace_publisher.json` already exists.

### 3. Sign the module

Every time you edit `module.json` or `handlers/handler.py`, re-run this:

```bash
cd ~/railcall-modules/stripe-ops
python3 sign_module.py
```

### 4. Deploy it into RailCall's modules folder

```bash
mkdir -p ~/.railcall/station/modules/stripe-ops/handlers
cp ~/railcall-modules/stripe-ops/module.json ~/.railcall/station/modules/stripe-ops/module.json
cp ~/railcall-modules/stripe-ops/module.sig ~/.railcall/station/modules/stripe-ops/module.sig
cp ~/railcall-modules/stripe-ops/handlers/handler.py ~/.railcall/station/modules/stripe-ops/handlers/handler.py
```

### 5. Make sure `requests` is installed for RailCall's Python

```bash
python3 -m pip install --user --break-system-packages --quiet requests
```

That's it — setup is done.

---

## Part 2 — every time you want to use it

You need **two terminal windows** left open, plus your browser.

### Terminal 1 — the real RailCall server

```bash
export PATH="$PATH:$HOME/.railcall/bin"
export STRIPE_SECRET_KEY=sk_test_...   # your Stripe test-mode key
python3 ~/.railcall/station/workbench/studio_server.py --no-open
```

Wait for `[modules] loaded=1 rejected=0` before continuing. If you see
`rejected=1`, you forgot to re-sign after an edit — go back to step 3.

### Terminal 2 — your control panel

```bash
cd ~/railcall-modules/stripe-ops/ui
python3 server.py
```

Wait for `stripe-ops control panel -> http://127.0.0.1:8900`.

### Browser

Open **http://127.0.0.1:8900**. Pick an action on the left, fill in the
form, and run it. Money-moving actions walk you through Preview → Approve
→ Execute; read-only ones just have a Run button.

---

## Troubleshooting

**"Address already in use" when starting a server**
Something from a previous session is still running on that port.
```bash
lsof -ti:8799 | xargs kill -9   # RailCall's own server
lsof -ti:8900 | xargs kill -9   # the control panel
```
Then start again.

**Control panel says "RailCall Studio not reachable on :8799"**
Terminal 1 isn't running, or you closed it. Go start it first — the panel
needs it to already be up.

**A command you edited shows up as rejected after reload**
You edited `module.json` or `handler.py` without re-signing. Run
`python3 sign_module.py` again, redeploy (step 4), then either restart
Terminal 1 or hit reload:
```bash
SESSION_TOKEN=$(cat ~/.railcall/station/.railcall_workspace/session_token)
curl -s -X POST http://127.0.0.1:8799/api/modules/reload \
  -H "X-RailCall-Session: $SESSION_TOKEN" -H "Content-Type: application/json" \
  -H "Origin: http://127.0.0.1:8799" -H "Referer: http://127.0.0.1:8799/v2" -d '{}'
```

**Need fresh fake test data to click around with**
Ask for it — the whole point of test mode is you can make as much fake
data as you want, at no cost and no risk.
