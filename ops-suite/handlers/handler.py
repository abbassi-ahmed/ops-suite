"""Handlers for the abbassi-ahmed/ops-suite module.

A single combined module: every Stripe and Twilio command from stripe-ops
and twilio-ops, plus the cross-provider billing-reminder composite from
billing-ops, merged into one signed bundle.

Auth: STRIPE_SECRET_KEY, TWILIO_ACCOUNT_SID, and TWILIO_AUTH_TOKEN are all
read from the environment. Never logged, never included in a return value,
never echoed in error messages.

Every command that mutates state (refunds, sends, cancellations, etc.) has
"mode": "write_requires_approval" in module.json, so RailCall's airlock
forces preview -> approve -> execute for it automatically. Every handler
function returns (result_dict, None) -- a bare dict would silently corrupt
the result (see the tuple-unpacking bug documented in this project's
original stripe-ops README).

Merge notes: stripe-ops and twilio-ops each defined a private `_request`
helper with different behavior (one calls the Stripe API, one calls
Twilio's). Merged into one file, those are renamed _stripe_ops_request and
_twilio_ops_request respectively to avoid one silently overwriting the
other. billing-ops's own _stripe_request/_stripe_key/_twilio_credentials/
_twilio_send helpers are kept separate and unchanged -- they're simpler,
self-contained implementations already used only by the three billing
composite commands, and don't collide with the renamed stripe-ops/
twilio-ops helpers.
"""

import os
import time
import uuid
import requests
from datetime import datetime, timezone


def _require(inputs: dict, field: str) -> str:
    value = inputs.get(field)
    if not value:
        raise ValueError(f"'{field}' is required and was not provided.")
    return value


# =============================================================================
# STRIPE-OPS commands
# =============================================================================

STRIPE_API_BASE = "https://api.stripe.com/v1"
REQUEST_TIMEOUT_SECONDS = 15


class StripeConfigError(RuntimeError):
    """Raised when the module is missing required configuration."""


class StripeAPIError(RuntimeError):
    """Raised when Stripe rejects a request. Message is safe to display."""


def _api_key() -> str:
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        raise StripeConfigError(
            "STRIPE_SECRET_KEY is not set. Run `railcall connect your-handle/stripe-ops` "
            "or set the STRIPE_SECRET_KEY environment variable to a Stripe secret key "
            "(sk_test_... for testing, sk_live_... for production)."
        )
    return key


def _stripe_ops_request(method: str, path: str, *, params: dict = None, data: dict = None,
             idempotency_key: str = None) -> dict:
    """Make one Stripe API request and return the parsed JSON body.

    Raises StripeAPIError with a clear, secret-free message on any
    non-2xx response instead of silently swallowing failures.
    """
    headers = {}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    try:
        response = requests.request(
            method,
            f"{STRIPE_API_BASE}{path}",
            auth=(_api_key(), ""),
            params=params,
            data=data,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        raise StripeAPIError(f"Network error calling Stripe ({path}): {exc}") from exc

    body = {}
    try:
        body = response.json()
    except ValueError:
        pass

    if response.status_code >= 400:
        stripe_message = (body.get("error") or {}).get("message") or response.text[:300]
        raise StripeAPIError(
            f"Stripe rejected {method} {path} (HTTP {response.status_code}): {stripe_message}"
        )

    return body


# ---------------------------------------------------------------------------
# Read-only commands (side_effects: none — run instantly, no airlock gate)
# ---------------------------------------------------------------------------

def list_charges(inputs: dict, context: dict) -> tuple:
    params = {"limit": min(max(int(inputs.get("limit", 10)), 1), 100)}
    customer_id = inputs.get("customer_id")
    if customer_id:
        params["customer"] = customer_id

    body = _stripe_ops_request("GET", "/charges", params=params)
    charges = [
        {
            "id": c["id"],
            "amount": c["amount"],
            "currency": c["currency"],
            "status": c["status"],
            "customer": c.get("customer"),
            "payment_intent": c.get("payment_intent"),
            "captured": c.get("captured"),
            "created": c["created"],
            "refunded": c.get("refunded", False),
        }
        for c in body.get("data", [])
    ]
    return {"charges": charges, "has_more": body.get("has_more", False)}, None


def get_customer(inputs: dict, context: dict) -> tuple:
    customer_id = _require(inputs, "customer_id")
    c = _stripe_ops_request("GET", f"/customers/{customer_id}")
    return {
        "id": c["id"],
        "email": c.get("email"),
        "name": c.get("name"),
        "balance": c.get("balance"),
        "currency": c.get("currency"),
        "delinquent": c.get("delinquent"),
    }, None


def search_customers(inputs: dict, context: dict) -> tuple:
    """Find customers by name and/or email using Stripe's Customer Search API
    (GET /v1/customers/search) -- the way to turn a person's name into their
    cus_ ID when you don't already have it."""
    clauses = []
    name = inputs.get("name")
    if name:
        clauses.append(f"name:'{name}'")
    email = inputs.get("email")
    if email:
        clauses.append(f"email:'{email}'")

    if not clauses:
        raise ValueError("Provide at least one of: name, email.")

    query = " AND ".join(clauses)
    body = _stripe_ops_request("GET", "/customers/search", params={"query": query, "limit": 20})
    customers = [
        {
            "id": c["id"],
            "name": c.get("name"),
            "email": c.get("email"),
            "delinquent": c.get("delinquent"),
        }
        for c in body.get("data", [])
    ]
    return {"customers": customers, "query_used": query}, None


def get_payment_intent(inputs: dict, context: dict) -> tuple:
    payment_intent_id = _require(inputs, "payment_intent_id")
    pi = _stripe_ops_request("GET", f"/payment_intents/{payment_intent_id}")
    return {
        "id": pi["id"],
        "status": pi.get("status"),
        "amount": pi.get("amount"),
        "amount_received": pi.get("amount_received"),
        "amount_capturable": pi.get("amount_capturable"),
        "currency": pi.get("currency"),
        "customer": pi.get("customer"),
        "latest_charge": pi.get("latest_charge"),
        "capture_method": pi.get("capture_method"),
    }, None


def list_disputes(inputs: dict, context: dict) -> tuple:
    params = {"limit": min(max(int(inputs.get("limit", 10)), 1), 100)}
    body = _stripe_ops_request("GET", "/disputes", params=params)
    disputes = [
        {
            "id": d["id"],
            "amount": d["amount"],
            "currency": d["currency"],
            "status": d["status"],
            "reason": d.get("reason"),
            "charge": d.get("charge"),
            "evidence_due_by": (d.get("evidence_details") or {}).get("due_by"),
        }
        for d in body.get("data", [])
    ]
    return {"disputes": disputes, "has_more": body.get("has_more", False)}, None


# ---------------------------------------------------------------------------
# Mutating commands (side_effects: external — airlock forces
# preview -> approve -> execute before these ever run)
# ---------------------------------------------------------------------------

def create_refund(inputs: dict, context: dict) -> tuple:
    charge_id = inputs.get("charge_id")
    payment_intent_id = inputs.get("payment_intent_id")
    if not charge_id and not payment_intent_id:
        raise ValueError("Provide either 'charge_id' or 'payment_intent_id'.")
    if charge_id and payment_intent_id:
        raise ValueError("Provide only one of 'charge_id' or 'payment_intent_id', not both.")

    data = {}
    if charge_id:
        data["charge"] = charge_id
    else:
        data["payment_intent"] = payment_intent_id

    amount_cents = inputs.get("amount_cents")
    if amount_cents is not None:
        if amount_cents <= 0:
            raise ValueError("'amount_cents' must be a positive integer.")
        data["amount"] = amount_cents

    reason = inputs.get("reason")
    if reason:
        allowed = {"duplicate", "fraudulent", "requested_by_customer"}
        if reason not in allowed:
            raise ValueError(f"'reason' must be one of {sorted(allowed)}, got {reason!r}.")
        data["reason"] = reason

    # Idempotency key derived from the refund target + amount so a retried
    # airlock execution can't double-refund the same charge.
    idem_source = f"{charge_id or payment_intent_id}:{amount_cents or 'full'}"
    idempotency_key = f"railcall-refund-{uuid.uuid5(uuid.NAMESPACE_URL, idem_source)}"

    body = _stripe_ops_request("POST", "/refunds", data=data, idempotency_key=idempotency_key)
    return {
        "refund_id": body["id"],
        "status": body["status"],
        "amount": body["amount"],
        "currency": body["currency"],
    }, None


def respond_to_dispute(inputs: dict, context: dict) -> tuple:
    dispute_id = _require(inputs, "dispute_id")
    evidence_text = _require(inputs, "evidence_text")
    submit = bool(inputs.get("submit", False))

    data = {"evidence[uncategorized_text]": evidence_text}
    if submit:
        data["submit"] = "true"

    body = _stripe_ops_request("POST", f"/disputes/{dispute_id}", data=data)
    return {
        "dispute_id": body["id"],
        "status": body["status"],
        "submitted": submit,
    }, None


def cancel_subscription(inputs: dict, context: dict) -> tuple:
    subscription_id = _require(inputs, "subscription_id")
    at_period_end = bool(inputs.get("at_period_end", True))

    if at_period_end:
        body = _stripe_ops_request(
            "POST",
            f"/subscriptions/{subscription_id}",
            data={"cancel_at_period_end": "true"},
        )
    else:
        body = _stripe_ops_request("DELETE", f"/subscriptions/{subscription_id}")

    return {
        "subscription_id": body["id"],
        "status": body["status"],
        "cancel_at_period_end": body.get("cancel_at_period_end", False),
        "canceled_at": body.get("canceled_at"),
    }, None


def capture_payment_intent(inputs: dict, context: dict) -> tuple:
    payment_intent_id = _require(inputs, "payment_intent_id")
    data = {}
    amount = inputs.get("amount_to_capture_cents")
    if amount is not None:
        if amount <= 0:
            raise ValueError("'amount_to_capture_cents' must be a positive integer.")
        data["amount_to_capture"] = amount

    idempotency_key = f"railcall-capture-{payment_intent_id}-{amount or 'full'}"
    body = _stripe_ops_request(
        "POST",
        f"/payment_intents/{payment_intent_id}/capture",
        data=data,
        idempotency_key=idempotency_key,
    )
    return {
        "payment_intent_id": body["id"],
        "status": body["status"],
        "amount_capturable": body.get("amount_capturable"),
        "amount_received": body.get("amount_received"),
    }, None


def cancel_payment_intent(inputs: dict, context: dict) -> tuple:
    payment_intent_id = _require(inputs, "payment_intent_id")
    data = {}
    reason = inputs.get("cancellation_reason")
    if reason:
        allowed = {"duplicate", "fraudulent", "requested_by_customer", "abandoned"}
        if reason not in allowed:
            raise ValueError(f"'cancellation_reason' must be one of {sorted(allowed)}, got {reason!r}.")
        data["cancellation_reason"] = reason

    body = _stripe_ops_request("POST", f"/payment_intents/{payment_intent_id}/cancel", data=data)
    return {
        "payment_intent_id": body["id"],
        "status": body["status"],
        "cancellation_reason": body.get("cancellation_reason"),
    }, None


def void_invoice(inputs: dict, context: dict) -> tuple:
    invoice_id = _require(inputs, "invoice_id")
    body = _stripe_ops_request("POST", f"/invoices/{invoice_id}/void")
    return {
        "invoice_id": body["id"],
        "status": body["status"],
    }, None


# ---------------------------------------------------------------------------
# Richer commands (side_effects varies) -- go beyond single-object CRUD:
# a real filtered search, a cross-object lookup, an urgency-sorted query,
# and two multi-step commands that bundle several Stripe calls behind one
# airlock preview so an operator approves the whole outcome once.
# ---------------------------------------------------------------------------

def search_charges(inputs: dict, context: dict) -> tuple:
    """Filtered charge search using Stripe's Search Query Language
    (GET /v1/charges/search), not just the plain list endpoint. Supports
    amount range, status, customer, and a created-date window -- combine
    any of them. Note: Stripe's search index can lag real-time writes by
    up to about a minute, so a charge created seconds ago may not appear
    yet (this is a Stripe platform limitation, not a bug here)."""
    clauses = []

    min_amount = inputs.get("min_amount_cents")
    if min_amount is not None:
        clauses.append(f"amount>={int(min_amount)}")
    max_amount = inputs.get("max_amount_cents")
    if max_amount is not None:
        clauses.append(f"amount<={int(max_amount)}")

    status = inputs.get("status")
    if status:
        allowed = {"succeeded", "pending", "failed"}
        if status not in allowed:
            raise ValueError(f"'status' must be one of {sorted(allowed)}, got {status!r}.")
        clauses.append(f"status:'{status}'")

    customer_id = inputs.get("customer_id")
    if customer_id:
        clauses.append(f"customer:'{customer_id}'")

    created_after = inputs.get("created_after")
    if created_after is not None:
        clauses.append(f"created>{int(created_after)}")
    created_before = inputs.get("created_before")
    if created_before is not None:
        clauses.append(f"created<{int(created_before)}")

    if not clauses:
        raise ValueError(
            "Provide at least one filter: min_amount_cents, max_amount_cents, "
            "status, customer_id, created_after, or created_before."
        )

    query = " AND ".join(clauses)
    limit = min(max(int(inputs.get("limit", 25)), 1), 100)
    body = _stripe_ops_request("GET", "/charges/search", params={"query": query, "limit": limit})
    charges = [
        {
            "id": c["id"],
            "amount": c["amount"],
            "currency": c["currency"],
            "status": c["status"],
            "customer": c.get("customer"),
            "payment_intent": c.get("payment_intent"),
            "captured": c.get("captured"),
            "created": c["created"],
            "refunded": c.get("refunded", False),
            "description": c.get("description"),
        }
        for c in body.get("data", [])
    ]
    return {
        "charges": charges,
        "query_used": query,
        "note": "Stripe's search index can take up to ~1 minute to catch up on very recent charges.",
    }, None


def customer_360(inputs: dict, context: dict) -> tuple:
    """One-call customer overview: profile + their 5 most recent charges +
    their subscriptions, joined together. Replaces having to run
    get_customer, list_charges, and a subscription lookup separately."""
    customer_id = _require(inputs, "customer_id")

    c = _stripe_ops_request("GET", f"/customers/{customer_id}")
    charges_body = _stripe_ops_request("GET", "/charges", params={"customer": customer_id, "limit": 5})
    subs_body = _stripe_ops_request("GET", "/subscriptions", params={"customer": customer_id, "limit": 5})

    recent_charges = [
        {
            "id": ch["id"],
            "amount": ch["amount"],
            "currency": ch["currency"],
            "status": ch["status"],
            "created": ch["created"],
            "refunded": ch.get("refunded", False),
        }
        for ch in charges_body.get("data", [])
    ]
    subscriptions = [
        {
            "id": s["id"],
            "status": s["status"],
            "current_period_end": s.get("current_period_end"),
            "cancel_at_period_end": s.get("cancel_at_period_end", False),
        }
        for s in subs_body.get("data", [])
    ]

    return {
        "customer": {
            "id": c["id"],
            "email": c.get("email"),
            "name": c.get("name"),
            "balance": c.get("balance"),
            "currency": c.get("currency"),
            "delinquent": c.get("delinquent"),
        },
        "recent_charges": recent_charges,
        "subscriptions": subscriptions,
    }, None


def list_disputes_due_soon(inputs: dict, context: dict) -> tuple:
    """Same data as list_disputes, but filtered + sorted by urgency: only
    disputes whose evidence deadline falls within the next N days (default
    7), soonest first -- so an ops person sees what actually needs action
    today instead of scanning every open dispute."""
    within_days = inputs.get("within_days")
    within_days = int(within_days) if within_days is not None else 7
    if within_days <= 0:
        raise ValueError("'within_days' must be a positive number.")

    cutoff = time.time() + within_days * 86400
    body = _stripe_ops_request("GET", "/disputes", params={"limit": 100})

    due_soon = []
    for d in body.get("data", []):
        due_by = (d.get("evidence_details") or {}).get("due_by")
        if due_by is None or due_by > cutoff:
            continue
        due_soon.append({
            "id": d["id"],
            "amount": d["amount"],
            "currency": d["currency"],
            "status": d.get("status"),
            "reason": d.get("reason"),
            "charge": d.get("charge"),
            "evidence_due_by": due_by,
        })
    due_soon.sort(key=lambda x: x["evidence_due_by"])

    return {"disputes_due_soon": due_soon, "within_days": within_days}, None


def bulk_refund(inputs: dict, context: dict) -> tuple:
    """Refund up to 25 charges in one airlock-approved action, instead of
    approving each refund one at a time. One bad charge_id doesn't stop the
    rest -- each attempt is tracked independently and both lists (refunded,
    failed) come back so nothing silently fails."""
    charge_ids = inputs.get("charge_ids")
    if not charge_ids or not isinstance(charge_ids, list):
        raise ValueError("'charge_ids' is required and must be a non-empty list of charge IDs.")
    if len(charge_ids) > 25:
        raise ValueError("Refund at most 25 charges per bulk_refund call.")

    reason = inputs.get("reason")
    if reason:
        allowed = {"duplicate", "fraudulent", "requested_by_customer"}
        if reason not in allowed:
            raise ValueError(f"'reason' must be one of {sorted(allowed)}, got {reason!r}.")

    refunded, failed = [], []
    for charge_id in charge_ids:
        idempotency_key = f"railcall-bulkrefund-{uuid.uuid5(uuid.NAMESPACE_URL, str(charge_id))}"
        data = {"charge": charge_id}
        if reason:
            data["reason"] = reason
        try:
            body = _stripe_ops_request("POST", "/refunds", data=data, idempotency_key=idempotency_key)
            refunded.append({
                "charge_id": charge_id, "refund_id": body["id"],
                "status": body["status"], "amount": body["amount"],
            })
        except StripeAPIError as exc:
            failed.append({"charge_id": charge_id, "error": str(exc)})

    return {"refunded": refunded, "failed": failed, "requested": len(charge_ids)}, None


def cancel_subscription_and_refund(inputs: dict, context: dict) -> tuple:
    """Multi-step: cancels a subscription AND refunds its most recent
    invoice's charge in one airlock-approved action -- the real "customer
    wants to cancel and get their last payment back" support request,
    instead of two separate approvals for cancel_subscription + create_refund."""
    subscription_id = _require(inputs, "subscription_id")
    at_period_end = bool(inputs.get("at_period_end", False))
    also_refund = inputs.get("also_refund_latest_invoice")
    also_refund = True if also_refund is None else bool(also_refund)

    if at_period_end:
        sub_body = _stripe_ops_request(
            "POST", f"/subscriptions/{subscription_id}",
            data={"cancel_at_period_end": "true"},
        )
    else:
        sub_body = _stripe_ops_request("DELETE", f"/subscriptions/{subscription_id}")

    result = {
        "subscription_id": sub_body["id"],
        "subscription_status": sub_body["status"],
        "cancel_at_period_end": sub_body.get("cancel_at_period_end", False),
        "refund_id": None,
        "refund_status": None,
        "refund_note": "not requested",
    }

    if not also_refund:
        return result, None

    latest_invoice_id = sub_body.get("latest_invoice")
    if not latest_invoice_id:
        result["refund_note"] = "subscription had no invoice to refund"
        return result, None

    invoice = _stripe_ops_request("GET", f"/invoices/{latest_invoice_id}")
    charge_id = invoice.get("charge")
    if not charge_id:
        payment_intent_id = invoice.get("payment_intent")
        if payment_intent_id:
            pi = _stripe_ops_request("GET", f"/payment_intents/{payment_intent_id}")
            charge_id = pi.get("latest_charge")

    if not charge_id:
        result["refund_note"] = "latest invoice has no associated charge (unpaid, or nothing to refund)"
        return result, None

    idempotency_key = f"railcall-cancelrefund-{subscription_id}"
    refund_body = _stripe_ops_request("POST", "/refunds", data={"charge": charge_id}, idempotency_key=idempotency_key)
    result["refund_id"] = refund_body["id"]
    result["refund_status"] = refund_body["status"]
    result["refund_note"] = f"refunded latest invoice's charge ({charge_id})"

    return result, None


# =============================================================================
# TWILIO-OPS commands
# =============================================================================

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"
REQUEST_TIMEOUT_SECONDS = 15


class TwilioConfigError(RuntimeError):
    """Raised when the module is missing required configuration."""


class TwilioAPIError(RuntimeError):
    """Raised when Twilio rejects a request. Message is safe to display."""


def _credentials() -> tuple:
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        raise TwilioConfigError(
            "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must both be set. "
            "Get them from the Twilio Console -> Account -> API keys & tokens."
        )
    return sid, token


def _twilio_ops_request(method: str, path: str, *, params: dict = None, data: dict = None) -> dict:
    """Make one Twilio API request and return the parsed JSON body.

    Raises TwilioAPIError with a clear, secret-free message on any
    non-2xx response instead of silently swallowing failures.
    """
    sid, token = _credentials()
    try:
        response = requests.request(
            method,
            f"{TWILIO_API_BASE}/Accounts/{sid}{path}",
            auth=(sid, token),
            params=params,
            data=data,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        raise TwilioAPIError(f"Network error calling Twilio ({path}): {exc}") from exc

    body = {}
    try:
        body = response.json()
    except ValueError:
        pass

    if response.status_code >= 400:
        twilio_message = body.get("message") or response.text[:300]
        raise TwilioAPIError(
            f"Twilio rejected {method} {path} (HTTP {response.status_code}): {twilio_message}"
        )

    return body


def _say_twiml(text: str) -> str:
    escaped = (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return f"<Response><Say>{escaped}</Say></Response>"


# ---------------------------------------------------------------------------
# Read-only commands -- run instantly, no airlock gate
# ---------------------------------------------------------------------------

def list_messages(inputs: dict, context: dict) -> tuple:
    params = {"PageSize": min(max(int(inputs.get("limit", 20)), 1), 100)}
    to = inputs.get("to")
    if to:
        params["To"] = to
    from_ = inputs.get("from")
    if from_:
        params["From"] = from_

    body = _twilio_ops_request("GET", "/Messages.json", params=params)
    messages = [
        {
            "sid": m["sid"],
            "to": m.get("to"),
            "from": m.get("from"),
            "body": m.get("body"),
            "status": m.get("status"),
            "direction": m.get("direction"),
            "date_sent": m.get("date_sent"),
            "price": m.get("price"),
        }
        for m in body.get("messages", [])
    ]
    return {"messages": messages}, None


def get_message(inputs: dict, context: dict) -> tuple:
    message_sid = _require(inputs, "message_sid")
    m = _twilio_ops_request("GET", f"/Messages/{message_sid}.json")
    return {
        "sid": m["sid"],
        "to": m.get("to"),
        "from": m.get("from"),
        "body": m.get("body"),
        "status": m.get("status"),
        "direction": m.get("direction"),
        "date_sent": m.get("date_sent"),
        "error_code": m.get("error_code"),
        "error_message": m.get("error_message"),
        "price": m.get("price"),
    }, None


def search_messages(inputs: dict, context: dict) -> tuple:
    params = {"PageSize": min(max(int(inputs.get("limit", 25)), 1), 100)}
    to = inputs.get("to")
    if to:
        params["To"] = to
    from_ = inputs.get("from")
    if from_:
        params["From"] = from_
    date_sent_after = inputs.get("date_sent_after")
    if date_sent_after:
        params["DateSent>"] = date_sent_after
    date_sent_before = inputs.get("date_sent_before")
    if date_sent_before:
        params["DateSent<"] = date_sent_before

    if len(params) == 1:
        raise ValueError(
            "Provide at least one filter: to, from, date_sent_after, or date_sent_before."
        )

    status = inputs.get("status")
    if status:
        allowed = {"queued", "sending", "sent", "failed", "delivered", "undelivered", "receiving", "received"}
        if status not in allowed:
            raise ValueError(f"'status' must be one of {sorted(allowed)}, got {status!r}.")

    body = _twilio_ops_request("GET", "/Messages.json", params=params)
    messages = [
        {
            "sid": m["sid"],
            "to": m.get("to"),
            "from": m.get("from"),
            "body": m.get("body"),
            "status": m.get("status"),
            "date_sent": m.get("date_sent"),
        }
        for m in body.get("messages", [])
        if not status or m.get("status") == status
    ]
    return {"messages": messages}, None


def list_calls(inputs: dict, context: dict) -> tuple:
    params = {"PageSize": min(max(int(inputs.get("limit", 20)), 1), 100)}
    to = inputs.get("to")
    if to:
        params["To"] = to

    body = _twilio_ops_request("GET", "/Calls.json", params=params)
    calls = [
        {
            "sid": c["sid"],
            "to": c.get("to"),
            "from": c.get("from"),
            "status": c.get("status"),
            "direction": c.get("direction"),
            "duration": c.get("duration"),
            "start_time": c.get("start_time"),
            "price": c.get("price"),
        }
        for c in body.get("calls", [])
    ]
    return {"calls": calls}, None


def account_usage(inputs: dict, context: dict) -> tuple:
    """One-call join of account balance + this-period usage records --
    saves running a Balance lookup and a Usage lookup separately."""
    balance = _twilio_ops_request("GET", "/Balance.json")
    usage_body = _twilio_ops_request("GET", "/Usage/Records/ThisMonth.json")

    usage = [
        {
            "category": u.get("category"),
            "count": u.get("count"),
            "usage": u.get("usage"),
            "price": u.get("price"),
            "price_unit": u.get("price_unit"),
        }
        for u in usage_body.get("usage_records", [])
        if float(u.get("price") or 0) != 0 or int(u.get("count") or 0) != 0
    ]

    return {
        "balance": balance.get("balance"),
        "currency": balance.get("currency"),
        "usage_this_month": usage,
    }, None


# ---------------------------------------------------------------------------
# Mutating commands -- airlock forces preview -> approve -> execute
# ---------------------------------------------------------------------------

def send_sms(inputs: dict, context: dict) -> tuple:
    to = _require(inputs, "to")
    from_ = _require(inputs, "from")
    body_text = _require(inputs, "body")

    data = {"To": to, "From": from_, "Body": body_text}
    m = _twilio_ops_request("POST", "/Messages.json", data=data)
    return {
        "sid": m["sid"],
        "status": m.get("status"),
        "to": m.get("to"),
        "from": m.get("from"),
    }, None


def make_call(inputs: dict, context: dict) -> tuple:
    to = _require(inputs, "to")
    from_ = _require(inputs, "from")
    say_text = _require(inputs, "say_text")

    data = {"To": to, "From": from_, "Twiml": _say_twiml(say_text)}
    c = _twilio_ops_request("POST", "/Calls.json", data=data)
    return {
        "sid": c["sid"],
        "status": c.get("status"),
        "to": c.get("to"),
        "from": c.get("from"),
    }, None


def bulk_send_sms(inputs: dict, context: dict) -> tuple:
    """Send the same message to up to 25 recipients in one airlock-approved
    action. One bad number doesn't stop the rest -- each attempt is tracked
    independently and both lists (sent, failed) come back."""
    to_numbers = inputs.get("to_numbers")
    if not to_numbers or not isinstance(to_numbers, list):
        raise ValueError("'to_numbers' is required and must be a non-empty list of phone numbers.")
    if len(to_numbers) > 25:
        raise ValueError("Send to at most 25 recipients per bulk_send_sms call.")

    from_ = _require(inputs, "from")
    body_text = _require(inputs, "body")

    sent, failed = [], []
    for to in to_numbers:
        try:
            m = _twilio_ops_request("POST", "/Messages.json", data={"To": to, "From": from_, "Body": body_text})
            sent.append({"to": to, "sid": m["sid"], "status": m.get("status")})
        except TwilioAPIError as exc:
            failed.append({"to": to, "error": str(exc)})

    return {"sent": sent, "failed": failed, "requested": len(to_numbers)}, None


def draft_and_send_sms(inputs: dict, context: dict) -> tuple:
    """The human-in-the-loop AI-draft pattern: renders a template with the
    given variables into the EXACT final message text, and that literal
    rendered text is what shows up in the airlock preview -- the operator
    reviews the actual words before anything sends, not just "a message will
    be sent to X". Uses simple {{var}} substitution, no external templating
    dependency."""
    to = _require(inputs, "to")
    from_ = _require(inputs, "from")
    template = _require(inputs, "template")
    variables = inputs.get("variables") or {}
    if not isinstance(variables, dict):
        raise ValueError("'variables' must be an object of {name: value} pairs.")

    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))

    if "{{" in rendered and "}}" in rendered:
        raise ValueError(
            "Template still contains an unresolved {{placeholder}} after substitution -- "
            "check that every variable used in the template was provided."
        )

    m = _twilio_ops_request("POST", "/Messages.json", data={"To": to, "From": from_, "Body": rendered})
    return {
        "sid": m["sid"],
        "status": m.get("status"),
        "rendered_message": rendered,
        "to": m.get("to"),
        "from": m.get("from"),
    }, None


def release_phone_number(inputs: dict, context: dict) -> tuple:
    """Deprovisions an owned Twilio number so it can never be used again.
    Irreversible -- once released, the number goes back into Twilio's
    general pool and cannot be reclaimed."""
    phone_number_sid = _require(inputs, "phone_number_sid")
    _twilio_ops_request("DELETE", f"/IncomingPhoneNumbers/{phone_number_sid}.json")
    return {
        "phone_number_sid": phone_number_sid,
        "status": "released",
    }, None


# =============================================================================
# BILLING-OPS commands (cross-provider composite)
# =============================================================================

STRIPE_API_BASE = "https://api.stripe.com/v1"
TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"
REQUEST_TIMEOUT_SECONDS = 15


class ConfigError(RuntimeError):
    """Raised when required credentials are missing."""


class ProviderAPIError(RuntimeError):
    """Raised when Stripe or Twilio rejects a request. Message is safe to display."""


def _stripe_key() -> str:
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        raise ConfigError(
            "STRIPE_SECRET_KEY is not set. Same credential stripe-ops uses -- "
            "export it in the terminal running the RailCall server."
        )
    return key


def _twilio_credentials() -> tuple:
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        raise ConfigError(
            "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must both be set. Same "
            "credentials twilio-ops uses -- export them in the terminal running "
            "the RailCall server."
        )
    return sid, token


def _stripe_request(method: str, path: str, *, params: dict = None) -> dict:
    try:
        response = requests.request(
            method,
            f"{STRIPE_API_BASE}{path}",
            auth=(_stripe_key(), ""),
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        raise ProviderAPIError(f"Network error calling Stripe ({path}): {exc}") from exc

    body = {}
    try:
        body = response.json()
    except ValueError:
        pass

    if response.status_code >= 400:
        stripe_message = (body.get("error") or {}).get("message") or response.text[:300]
        raise ProviderAPIError(
            f"Stripe rejected {method} {path} (HTTP {response.status_code}): {stripe_message}"
        )
    return body


def _twilio_send(to: str, from_: str, body_text: str) -> dict:
    sid, token = _twilio_credentials()
    try:
        response = requests.post(
            f"{TWILIO_API_BASE}/Accounts/{sid}/Messages.json",
            auth=(sid, token),
            data={"To": to, "From": from_, "Body": body_text},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        raise ProviderAPIError(f"Network error calling Twilio (Messages.json): {exc}") from exc

    body = {}
    try:
        body = response.json()
    except ValueError:
        pass

    if response.status_code >= 400:
        twilio_message = body.get("message") or response.text[:300]
        raise ProviderAPIError(
            f"Twilio rejected POST /Messages.json (HTTP {response.status_code}): {twilio_message}"
        )
    return body


# ---------------------------------------------------------------------------
# Shared invoice logic -- used by both preview_invoice_reminder (read-only)
# and send_invoice_reminder_sms (write), so the two commands can never drift
# apart on what the "real" message text is.
# ---------------------------------------------------------------------------

_UNSENDABLE_STATUSES = {
    "paid": "this invoice is already paid -- nothing to remind about.",
    "void": "this invoice was voided -- nothing to remind about.",
    "uncollectible": "this invoice is marked uncollectible -- a reminder won't help; contact the customer directly.",
    "draft": "this invoice is still a draft (not sent to the customer yet) -- finalize it in Stripe first.",
}


def _fetch_invoice_for_reminder(invoice_id: str) -> dict:
    invoice = _stripe_request("GET", f"/invoices/{invoice_id}")

    status = invoice.get("status")
    if status in _UNSENDABLE_STATUSES:
        raise ValueError(f"Can't send a reminder for invoice {invoice_id}: {_UNSENDABLE_STATUSES[status]}")

    amount_due = invoice.get("amount_due") or 0
    if amount_due <= 0:
        raise ValueError(f"Invoice {invoice_id} has no amount due -- nothing to remind about.")

    return invoice


def _render_reminder_text(invoice: dict, custom_note: str = None) -> str:
    amount = f"{(invoice.get('amount_due') or 0) / 100:.2f}"
    currency = str(invoice.get("currency") or "").upper()
    name = invoice.get("customer_name") or invoice.get("customer_email") or "there"
    url = invoice.get("hosted_invoice_url") or ""
    due_date = invoice.get("due_date")

    if due_date:
        due_str = datetime.fromtimestamp(due_date, tz=timezone.utc).strftime("%b %d, %Y")
        text = f"Hi {name}, this is a reminder that your invoice for {amount} {currency} is due {due_str}."
    else:
        text = f"Hi {name}, this is a reminder that you have an open invoice for {amount} {currency}."

    if url:
        text += f" Pay here: {url}"
    if custom_note:
        text += f" {custom_note}"
    return text


def _invoice_summary(invoice: dict) -> dict:
    return {
        "invoice_id": invoice.get("id"),
        "status": invoice.get("status"),
        "customer_id": invoice.get("customer"),
        "customer_name": invoice.get("customer_name"),
        "customer_email": invoice.get("customer_email"),
        "amount_due": invoice.get("amount_due"),
        "currency": invoice.get("currency"),
        "due_date": invoice.get("due_date"),
        "hosted_invoice_url": invoice.get("hosted_invoice_url"),
    }


# ---------------------------------------------------------------------------
# Read-only commands -- run instantly, no airlock gate
# ---------------------------------------------------------------------------

def list_invoices_needing_reminder(inputs: dict, context: dict) -> tuple:
    within_days = inputs.get("within_days")
    within_days = int(within_days) if within_days is not None else 7
    if within_days <= 0:
        raise ValueError("'within_days' must be a positive number.")

    cutoff = time.time() + within_days * 86400
    body = _stripe_request("GET", "/invoices", params={"status": "open", "limit": 100})

    due = []
    for inv in body.get("data", []):
        due_date = inv.get("due_date")
        if due_date is None or due_date > cutoff:
            continue
        due.append(_invoice_summary(inv))
    due.sort(key=lambda x: x["due_date"])

    return {"invoices_needing_reminder": due, "within_days": within_days}, None


def preview_invoice_reminder(inputs: dict, context: dict) -> tuple:
    invoice_id = _require(inputs, "invoice_id")
    to = _require(inputs, "to")
    custom_note = inputs.get("custom_note")

    invoice = _fetch_invoice_for_reminder(invoice_id)
    rendered = _render_reminder_text(invoice, custom_note)

    result = _invoice_summary(invoice)
    result["would_send_to"] = to
    result["rendered_message"] = rendered
    result["note"] = "Nothing was sent. Run send_invoice_reminder_sms with the same inputs to actually send this."
    return result, None


# ---------------------------------------------------------------------------
# Mutating command -- airlock forces preview -> approve -> execute. Touches
# TWO providers (Stripe read, Twilio write) behind that single approval.
# ---------------------------------------------------------------------------

def send_invoice_reminder_sms(inputs: dict, context: dict) -> tuple:
    invoice_id = _require(inputs, "invoice_id")
    to = _require(inputs, "to")
    from_ = _require(inputs, "from")
    custom_note = inputs.get("custom_note")

    invoice = _fetch_invoice_for_reminder(invoice_id)
    rendered = _render_reminder_text(invoice, custom_note)

    m = _twilio_send(to, from_, rendered)

    result = _invoice_summary(invoice)
    result["sent_to"] = to
    result["sent_from"] = from_
    result["rendered_message"] = rendered
    result["message_sid"] = m.get("sid")
    result["message_status"] = m.get("status")
    return result, None
