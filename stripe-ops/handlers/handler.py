"""Handlers for the your-handle/stripe-ops module.

Wraps the Stripe REST API directly (no stripe-python dependency, just
`requests`) so support/finance ops teams can run refunds, dispute
responses, subscription cancellations, invoice voids, and account
lookups through RailCall's airlock instead of the Stripe dashboard.

Auth: STRIPE_SECRET_KEY is read from the environment (set via
`railcall connect` / the env var prompt on install, per module.json's
"auth": {"type": "api_key", "env_var": "STRIPE_SECRET_KEY"}).
The key is used only inside the request's Basic Auth header. It is
never logged, never included in a return value, and never echoed back
in error messages.

Every command that moves money or otherwise mutates Stripe state has
"side_effects": "external" in module.json, so the RailCall airlock
forces preview -> approve -> execute for it automatically. The
functions below don't call the airlock themselves -- they just do the
work and return data, exactly as the RailCall docs describe.
"""

import os
import time
import uuid

import requests

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


def _request(method: str, path: str, *, params: dict = None, data: dict = None,
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


def _require(inputs: dict, field: str) -> str:
    value = inputs.get(field)
    if not value:
        raise ValueError(f"'{field}' is required and was not provided.")
    return value


# ---------------------------------------------------------------------------
# Read-only commands (side_effects: none — run instantly, no airlock gate)
# ---------------------------------------------------------------------------

def list_charges(inputs: dict, context: dict) -> tuple:
    params = {"limit": min(max(int(inputs.get("limit", 10)), 1), 100)}
    customer_id = inputs.get("customer_id")
    if customer_id:
        params["customer"] = customer_id

    body = _request("GET", "/charges", params=params)
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
    c = _request("GET", f"/customers/{customer_id}")
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
    body = _request("GET", "/customers/search", params={"query": query, "limit": 20})
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
    pi = _request("GET", f"/payment_intents/{payment_intent_id}")
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
    body = _request("GET", "/disputes", params=params)
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

    body = _request("POST", "/refunds", data=data, idempotency_key=idempotency_key)
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

    body = _request("POST", f"/disputes/{dispute_id}", data=data)
    return {
        "dispute_id": body["id"],
        "status": body["status"],
        "submitted": submit,
    }, None


def cancel_subscription(inputs: dict, context: dict) -> tuple:
    subscription_id = _require(inputs, "subscription_id")
    at_period_end = bool(inputs.get("at_period_end", True))

    if at_period_end:
        body = _request(
            "POST",
            f"/subscriptions/{subscription_id}",
            data={"cancel_at_period_end": "true"},
        )
    else:
        body = _request("DELETE", f"/subscriptions/{subscription_id}")

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
    body = _request(
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

    body = _request("POST", f"/payment_intents/{payment_intent_id}/cancel", data=data)
    return {
        "payment_intent_id": body["id"],
        "status": body["status"],
        "cancellation_reason": body.get("cancellation_reason"),
    }, None


def void_invoice(inputs: dict, context: dict) -> tuple:
    invoice_id = _require(inputs, "invoice_id")
    body = _request("POST", f"/invoices/{invoice_id}/void")
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
    body = _request("GET", "/charges/search", params={"query": query, "limit": limit})
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

    c = _request("GET", f"/customers/{customer_id}")
    charges_body = _request("GET", "/charges", params={"customer": customer_id, "limit": 5})
    subs_body = _request("GET", "/subscriptions", params={"customer": customer_id, "limit": 5})

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
    body = _request("GET", "/disputes", params={"limit": 100})

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
            body = _request("POST", "/refunds", data=data, idempotency_key=idempotency_key)
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
        sub_body = _request(
            "POST", f"/subscriptions/{subscription_id}",
            data={"cancel_at_period_end": "true"},
        )
    else:
        sub_body = _request("DELETE", f"/subscriptions/{subscription_id}")

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

    invoice = _request("GET", f"/invoices/{latest_invoice_id}")
    charge_id = invoice.get("charge")
    if not charge_id:
        payment_intent_id = invoice.get("payment_intent")
        if payment_intent_id:
            pi = _request("GET", f"/payment_intents/{payment_intent_id}")
            charge_id = pi.get("latest_charge")

    if not charge_id:
        result["refund_note"] = "latest invoice has no associated charge (unpaid, or nothing to refund)"
        return result, None

    idempotency_key = f"railcall-cancelrefund-{subscription_id}"
    refund_body = _request("POST", "/refunds", data={"charge": charge_id}, idempotency_key=idempotency_key)
    result["refund_id"] = refund_body["id"]
    result["refund_status"] = refund_body["status"]
    result["refund_note"] = f"refunded latest invoice's charge ({charge_id})"

    return result, None
