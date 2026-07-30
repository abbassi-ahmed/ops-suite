# Demo video script

Short narration lines for each action, in the same order they appear in
the control panel's sidebar. Read naturally, pause where you'd actually
click something.

## Intro

"This is Stripe Ops — a module I built for RailCall's marketplace contest.
It lets a support or finance team run real Stripe actions, but anything
that touches money has to be previewed and approved by a human first, and
every action leaves a permanent, signed record. Let me show you."

---

## Reads (instant, no approval needed)

**customer_360**
"customer_360 is a shortcut. Instead of three separate lookups, one call
gives me a customer's profile, their recent payments, and their
subscriptions, all together."

**get_customer**
"get_customer looks up one customer — their name, email, balance, and
whether they're behind on payments."

**list_charges**
"list_charges pulls up recent payments instantly. I can filter by a
specific customer, or just see the latest ones."

**list_disputes**
"list_disputes shows any payments a customer has disputed with their bank
— a chargeback — so support knows what needs attention."

**list_disputes_due_soon**
"list_disputes_due_soon filters that down to just the ones with a deadline
coming up soon, most urgent first — so nothing gets missed."

**search_charges**
"search_charges is a smarter search — I can filter by amount range,
status, a specific customer, or a date window, instead of just scrolling
through everything."

---

## Writes (preview → approve → execute, every time)

**bulk_refund**
"Now the money-moving side. bulk_refund handles a whole batch of refunds
in one approval. I approve the batch once, and each refund is tracked
individually — success or failure, nothing gets silently missed."

**cancel_subscription**
"cancel_subscription cancels a subscription, right away or at the end of
the billing period — previewed and approved before it happens."

**cancel_subscription_and_refund**
"cancel_subscription_and_refund is the real 'customer wants to cancel and
get their money back' request, done in one step instead of two separate
approvals."

**capture_payment_intent**
"capture_payment_intent is for payments that were only held, not collected
yet. This is the moment the money actually moves, so it goes through the
same approval step."

**create_refund**
"create_refund refunds a customer. Watch — before anything happens, it
shows me exactly what's about to be refunded. Only after I approve does it
actually call Stripe — and here's the signed receipt, proof of exactly
what happened."

**respond_to_dispute**
"respond_to_dispute sends evidence to fight a dispute. Same pattern — I
write it, preview it, approve it, and only then does it actually submit."

**void_invoice**
"void_invoice cancels an unpaid invoice. And if I try to void one that's
already been paid — watch — Stripe correctly refuses, and it tells me
exactly why instead of pretending it worked."

---

## Outro

"Every action here, read or write, leaves a permanent signed record.
Nothing fails silently, and money never moves without a human saying yes
first. That's Stripe Ops."
