# Demo video script

Short narration lines for each action, in the same order they'll appear
in the control panel's sidebar.

## Intro

"This is Twilio Ops — a second module I built for RailCall's marketplace
contest, this time for SMS and voice. Same idea as the Stripe one: nothing
that costs money or reaches a real person goes out without a human
approving it first, and every action leaves a signed record."

---

## Reads (instant, no approval needed)

**account_usage**
"account_usage shows my balance and this month's usage in one look —
texts sent, calls made, and what they cost."

**get_message**
"get_message looks up one text message and shows its full status — handy
for checking whether something actually went through."

**list_calls**
"list_calls shows recent voice calls — who was called, how long it
lasted, and the cost."

**list_messages**
"list_messages shows recent texts — instantly, no approval needed since
it's just reading data."

**search_messages**
"search_messages is a smarter search — by number, date range, or status,
instead of scrolling through everything."

---

## Writes (preview → approve → execute, every time)

**bulk_send_sms**
"bulk_send_sms sends the same message to a whole list of people in one
approval. Each one is tracked individually — who it reached, who failed."

**draft_and_send_sms**
"And here's the important one — draft_and_send_sms. I give it a template
and some values, and watch — it shows me the exact final message, word
for word, before anything sends. If an AI wrote this, I'm reviewing the
AI's actual words, not just approving a vague 'send a message' action."

**make_call**
"make_call places a real phone call that reads a message out loud. Same
rule — preview, approve, then it actually dials."

**release_phone_number**
"release_phone_number permanently gives up one of my Twilio numbers — no
undo. I built and verified this one carefully, but I'm not running it for
real on camera, since I only have the one number."

**send_sms**
"send_sms sends one text. Watch — before anything happens, it shows me
exactly who it's going to and exactly what it says. Only after I approve
does it actually send — and here's the signed receipt."

---

## Outro

"Same pattern as the Stripe module, applied to a completely different
problem: nothing risky happens without a human seeing the exact thing
first, and everything leaves proof. That's Twilio Ops."
