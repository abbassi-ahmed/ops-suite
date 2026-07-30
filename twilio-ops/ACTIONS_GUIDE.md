# Twilio Ops — plain English guide

This explains what each of the 10 actions does, in simple words. Just for
you — separate from the official contest README.

There are two kinds of actions:
- **Look-only actions** (5) — just show you information. Nothing changes,
  nothing to approve, runs instantly.
- **Send actions** (5) — actually send a real message or call, or change
  your Twilio account. These always show you exactly what's about to
  happen first, and wait for you to click Approve. Every action leaves a
  permanent, signed record.

---

## Look-only actions (safe, instant)

### `list_messages` — "Show me recent texts"
**What it does:** Shows a list of recent SMS messages sent or received.
**What you tell it:** (optional) a specific number to filter by, how many
results.
**What you get back:** Each message's ID, who it's to/from, the text,
whether it was delivered, and when.

### `get_message` — "Show me one specific text"
**What it does:** Looks up one message and shows its full status —
useful for checking if a message actually went through, or why it failed.
**What you tell it:** That message's ID.
**What you get back:** Its text, status, and if it failed, the exact
error Twilio gave.

### `list_calls` — "Show me recent phone calls"
**What it does:** Shows a list of recent voice calls.
**What you tell it:** (optional) a specific number, how many results.
**What you get back:** Each call's ID, who it's to/from, how long it
lasted, and its cost.

### `search_messages` — "Find specific texts"
**What it does:** A smarter version of `list_messages` — narrow down by
date range and status, not just scroll through everything.
**What you tell it:** Any combination of a number, a date range, or a
status (like "failed" or "delivered").
**What you get back:** Just the messages matching your filters.

### `account_usage` — "How much am I spending?"
**What it does:** Shows your account balance and this month's usage, all
in one look, instead of checking two separate pages.
**What you tell it:** Nothing — just run it.
**What you get back:** Your balance, and a breakdown of what you've used
this month (texts sent, calls made, and their cost).

---

## Send actions (need your approval every time)

### `send_sms` — "Send one text message" ⚠️ high risk
**What it does:** Sends a text message to one person.
**What you tell it:** Who to send it to, which of your Twilio numbers to
send from, and the exact text.
**What you get back:** The message's ID and its status.
**Why it needs approval:** Real money, and a real message landing on a
real phone — worth a look before it's irreversible.

### `make_call` — "Call someone with a message" ⚠️ high risk
**What it does:** Places a phone call that reads a short message out loud
when answered.
**What you tell it:** Who to call, which number to call from, and the
exact words to be read aloud.
**What you get back:** The call's ID and its status.
**Why it needs approval:** Same reason as a text — a real call to a real
person, costs money, worth confirming first.

### `bulk_send_sms` — "Text a whole group at once" ⚠️ high risk
**What it does:** Sends the same message to a list of people in one go,
instead of approving each one separately.
**What you tell it:** A list of phone numbers (up to 25), which number to
send from, and the message.
**What you get back:** Two lists — who it actually reached, and who
failed (with why) — so nothing gets silently missed.
**Why it needs approval:** Same risk as one text, just multiplied across
a whole group.

### `draft_and_send_sms` — "Review the exact words before sending" ⚠️ high risk
**What it does:** This is the important one. You give it a template like
"Hi {{name}}, your order {{order_id}} shipped!" plus the actual values,
and it shows you the **exact final message** — word for word — before
anything sends. If an AI wrote the template, you're reviewing the AI's
actual words, not just approving a vague "send a message" action.
**What you tell it:** Who to send to, which number to send from, the
template, and the values to fill in.
**What you get back:** The real sent message text, its ID, and status.
**Why it needs approval:** This is exactly the kind of safety net that
matters when a message might have been drafted by an AI — a human reads
the real words before a customer does.

### `release_phone_number` — "Permanently give up a phone number" ⚠️ high risk
**What it does:** Deprovisions one of your Twilio phone numbers so it can
never be used again.
**What you tell it:** The number's internal ID (not the phone number
itself).
**Why it needs approval:** Once released, that number is gone for good —
no undo. (We built and checked this one carefully but never actually ran
it for real, so we wouldn't accidentally lose the only test number.)

---

## Where to run these

Open your control panel at **http://127.0.0.1:8901** (a different port
than the Stripe one, so both can run at the same time). Look-only actions
have one **Run** button. Send actions have three buttons in order:
**Preview** → **Approve** → **Execute**.
