# Stripe Ops — plain English guide

This explains what each of the 13 actions does, in simple words. This is
just for you — it's separate from the official contest README (that one has
to stay short and technical for the judges).

There are two kinds of actions:
- **Look-only actions** (6 of them) — just show you information. Nothing
  changes, nothing to approve, runs instantly.
- **Money-moving actions** (7 of them) — actually change something in
  Stripe. These always show you exactly what's about to happen first, and
  wait for you to click Approve before anything really happens. Every action
  also leaves a permanent, signed record of what happened.

---

## Look-only actions (safe, instant)

### 1. `list_charges` — "Show me recent payments"
**What it does:** Shows a list of recent payments people have made.
**What you tell it:** (optional) a specific customer to filter by, and how
many results you want (up to 100).
**What you get back:** A list of payments — for each one: its ID, how much
money, what currency, whether it succeeded, which customer paid, when it
happened, and whether it's already been refunded.

### 2. `get_customer` — "Show me one customer"
**What it does:** Looks up one specific customer and shows their basic info.
**What you tell it:** That customer's ID.
**What you get back:** Their ID, email, name, account balance, currency, and
whether they're behind on payments.

### 3. `list_disputes` — "Show me chargebacks"
**What it does:** Shows payments that customers have disputed with their
bank (also called chargebacks).
**What you tell it:** How many results you want.
**What you get back:** For each dispute: its ID, the amount, currency,
current status, the reason given, which payment it's about, and the
deadline for you to respond.

### 4. `search_charges` — "Find specific payments"
**What it does:** A smarter version of `list_charges` — lets you narrow
down exactly which payments you're looking for instead of scrolling
through everything.
**What you tell it:** Any combination of: a minimum/maximum amount, a
status (`succeeded`, `pending`, or `failed`), a specific customer, or a
date range. You only need to fill in the filters you care about.
**What you get back:** The matching payments, same shape as `list_charges`.
**Good to know:** payments made in the last minute or so might not show up
yet — that's a small delay on Stripe's own search system, not a bug.

### 5. `customer_360` — "Everything about one customer, at once"
**What it does:** Instead of looking up a customer, then separately
looking up their payments, then separately looking up their subscriptions,
this gets all three in one go.
**What you tell it:** The customer's ID.
**What you get back:** Their profile, their 5 most recent payments, and
their subscriptions — all together.

### 6. `list_disputes_due_soon` — "What needs my attention today?"
**What it does:** Same as `list_disputes`, but only shows the ones with a
response deadline coming up soon, with the most urgent one first — so you
don't have to scan every open dispute to find what's time-sensitive.
**What you tell it:** How many days ahead to look (defaults to 7).
**What you get back:** Just the disputes due within that window, soonest
deadline first.

---

## Money-moving actions (need your approval every time)

### 7. `create_refund` — "Give money back" ⚠️ high risk
**What it does:** Refunds a customer — either the whole payment or part of it.
**What you tell it:** Which payment to refund, optionally how much (leave
blank to refund the full amount), and why (must be one of: `duplicate`,
`fraudulent`, or `requested_by_customer`).
**What you get back:** A refund ID, its status, how much was refunded, and
the currency.
**Why it needs approval:** This is real money leaving the business — you
should always double-check the payment and amount before it happens.

### 8. `respond_to_dispute` — "Fight back on a chargeback" ⚠️ medium risk
**What it does:** Sends your explanation to Stripe, arguing that a disputed
payment was legitimate.
**What you tell it:** Which dispute, your written explanation, and whether
to submit it now or just save it as a draft for later.
**What you get back:** The dispute's ID, its new status, and whether it was
actually sent.
**Why it needs approval:** What you write here directly affects whether you
win or lose the dispute — worth a second look before it's sent.

### 9. `cancel_subscription` — "Stop a subscription" ⚠️ high risk
**What it does:** Cancels a customer's recurring subscription.
**What you tell it:** Which subscription, and whether to cancel it right now
or let it run until the customer's current billing period ends.
**What you get back:** The subscription's ID, its new status, whether it's
set to end at period-end, and when it was canceled.
**Why it needs approval:** This stops future revenue from that customer —
an easy thing to want a second opinion on.

### 10. `capture_payment_intent` — "Actually take the money" ⚠️ high risk
**What it does:** Some payments are only "held" (authorized but not
collected yet) — this actually takes the money.
**What you tell it:** Which payment, and optionally a smaller amount if you
don't want to take the full amount.
**What you get back:** The payment's ID, its status, how much is still
available to capture, and how much was actually collected.
**Why it needs approval:** This is the moment real money actually moves —
worth confirming first.

### 11. `void_invoice` — "Cancel an unpaid bill" ⚠️ medium risk
**What it does:** Cancels an invoice that hasn't been paid yet, so it can
never be collected.
**What you tell it:** Which invoice.
**What you get back:** The invoice's ID and its new status.
**Why it needs approval:** Once voided, that invoice can't be paid — good to
confirm you picked the right one.

### 12. `bulk_refund` — "Refund a batch of payments at once" ⚠️ high risk
**What it does:** Refunds several payments in one go, instead of clicking
Approve separately for each one. Useful when something went wrong for a
whole group of customers at once (a pricing bug, a duplicate-charge
incident, etc.).
**What you tell it:** A list of payment IDs (up to 25), and optionally why.
**What you get back:** Two lists — which ones were successfully refunded,
and which ones failed (with the reason why), so nothing gets silently
missed.
**Why it needs approval:** Same reason as a single refund, just multiplied
— you see the whole batch before anything happens.

### 13. `cancel_subscription_and_refund` — "Cancel and give the last payment back" ⚠️ high risk
**What it does:** The real "customer wants to quit AND wants their money
back" request, done in one step: cancels the subscription, then refunds
their most recent payment for it — instead of you having to run
`cancel_subscription` and `create_refund` separately.
**What you tell it:** Which subscription, whether to cancel immediately or
at the end of the billing period, and whether you also want the refund
(on by default).
**What you get back:** The subscription's new status, plus the refund's ID
and status if one happened.
**Known limitation:** on some Stripe accounts, this can't always
automatically find the exact payment tied to a subscription's most recent
bill (a quirk of how newer Stripe versions structure that data). When that
happens, it honestly tells you "nothing to refund" instead of guessing —
guessing wrong here could mean refunding the wrong payment, which is worse
than just telling you to do it manually via `create_refund`.
**Why it needs approval:** It moves money and permanently cancels billing
in the same step — the airlock shows you both parts before you approve.

---

## Where to run these

Open your control panel at **http://127.0.0.1:8900** (see the other guide
for how to start it). Look-only actions have one **Run** button. Money-moving
actions have three buttons in order: **Preview** (shows exactly what will
happen) → **Approve** (you say "yes, do it") → **Execute** (it actually
happens). You'll see the result right there, and it also shows up in the
"Recent receipts" list at the bottom of the page.
