"""Handlers for the your-handle/billing-ops module.

A cross-provider composite on top of the same real accounts stripe-ops and
twilio-ops use: looks up a real Stripe invoice and sends its exact amount,
due date, and payment link as an SMS via Twilio. One Stripe call + one
Twilio call, one airlock approval.

This module is self-contained on purpose -- RailCall modules can only be
module.json + handlers/handler.py + module.sig, so it does NOT import
stripe-ops's or twilio-ops's handler.py. The small amount of duplicated
`_request` HTTP-calling code below is deliberate, not an oversight.

Auth: STRIPE_SECRET_KEY, TWILIO_ACCOUNT_SID, and TWILIO_AUTH_TOKEN are all
read from the environment. Same non-negotiables as the other two modules:
never logged, never included in a return value, never echoed in errors.

IMPORTANT, and worth documenting honestly: RailCall's own airlock preview
(GET /api/commands/preview) only echoes back the raw inputs you typed --
it never calls a module's handler function before approval (confirmed by
reading studio_server.py's preview_command() and approval_airlock.py's
airlock_card(), where "payload": redact(inputs) is literally just the
input dict). So for send_invoice_reminder_sms, the standard airlock
preview step can NOT show you the real invoice amount or the literal SMS
text before you approve -- only invoice_id/to/from/custom_note as typed.
That's why preview_invoice_reminder exists as its own read-only command:
it does the exact same Stripe fetch + render as the real send, just
without the Twilio call, so you can genuinely see the real words first.

Every handler function returns (result_dict, None) -- a bare dict would
silently corrupt the result the same way the original stripe-ops bug did
(see stripe-ops/README.md section 2).
"""

import os
import time
from datetime import datetime, timezone

import requests

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


def _require(inputs: dict, field: str) -> str:
    value = inputs.get(field)
    if not value:
        raise ValueError(f"'{field}' is required and was not provided.")
    return value


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
