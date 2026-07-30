# twilio-ops — airlock-gated Twilio module for RailCall

## What it does

10 commands covering SMS and voice operations a support/ops team actually
runs — not just single-message CRUD:

**Reads (5, instant, no approval):** `list_messages`, `get_message`,
`list_calls`, plus `search_messages` (filtered by to/from/date range/
status — richer than a plain list) and `account_usage` (balance + this
month's usage records, joined in one call).

**Writes (5, airlock-gated):** `send_sms`, `make_call`, plus
`bulk_send_sms` (up to 25 recipients in one approval, independent per-
recipient success/failure tracking), `draft_and_send_sms` (renders a
`{{template}}` + variables into the exact final message text and shows
that literal text in the preview — RailCall's own "AI drafts, human
reviews the words" category C example), and `release_phone_number`
(deprovisions a number — irreversible).

Every write command is flagged so RailCall's airlock forces a preview of
exactly what will happen — the real message body, the real recipient —
before anyone can approve it, and every execution gets a signed receipt.

## Who it's for

A support or ops person who currently sends SMS/voice blasts by hand or via
a script with no review step — a wrong recipient, a bad AI-drafted
message, or an accidental bulk send are real, costly, and sometimes
compliance-relevant mistakes. This gives them a "someone has to see the
exact words before they go out" gate, plus a signed receipt for every send.

## Install

```
railcall market install your-handle/twilio-ops
railcall connect your-handle/twilio-ops   # prompts for Twilio credentials
```

Use a Twilio **trial account** to try it safely — trial accounts can only
send to phone numbers you've verified as a caller ID in the Twilio Console
first (Console → Phone Numbers → Verified Caller IDs).

## Example

Every command runs from a plain terminal — no browser required. Start
`railcall studio --no-open` with the Twilio credentials exported, then
use `railcall_term.py` (in the root of this repo) to drive the same
preview → approve → execute airlock the browser UI uses:

```
python3 railcall_term.py twilio-ops.list_messages --limit=5
# → {"messages": [{"sid": "SM1a2...", "to": "+15551234567",
#     "from": "+15557654321", "body": "Hi there", "status": "delivered",
#     "date_sent": "2026-07-27T12:00:00Z"}]}

python3 railcall_term.py twilio-ops.draft_and_send_sms \
  --to=+15551234567 --from=+15557654321 \
  --template="Hi {{name}}, your order {{order_id}} shipped!" \
  --variables='{"name":"Alex","order_id":"1042"}'
# → prints the exact rendered text: "Hi Alex, your order 1042 shipped!"
# → Approve and execute the above? [y/N] y
# → prints the signed receipt: {"sid": "SM9f3...", "status": "queued",
#     "rendered_message": "Hi Alex, your order 1042 shipped!"}
```

## Credentials needed

Two environment variables: `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN`,
from the Twilio Console → Account → API keys & tokens. Used only in the
request's Basic Auth header — never logged, returned, or included in
error messages.

## Known limitations

- Twilio's Messages/Calls creation endpoints are **not idempotent** (per
  Twilio's own docs) — a retried `send_sms`/`make_call` after a timeout
  could send twice. Unlike Stripe's refund idempotency keys, Twilio has no
  equivalent here, so this is disclosed rather than falsely guaranteed.
- Trial accounts require every `to`/`from` number to be a verified caller
  ID — an unverified number fails with a clear Twilio error, not silently.
- `release_phone_number` was schema/signature-verified but not run for
  real, to avoid deprovisioning the only number on a test account.
- No pagination cursor support (`limit` capped at 100).

## Tag

`contest:2026Q3`
