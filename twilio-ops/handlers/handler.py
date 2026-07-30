"""Handlers for the your-handle/twilio-ops module.

Wraps the Twilio REST API directly (no twilio-python dependency, just
`requests`) so support/ops teams can send SMS, place calls, and look up
message/call history through RailCall's airlock instead of firing scripts
with no human checkpoint.

Auth: TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are read from the
environment. They are used only inside the request's Basic Auth header
(SID as username, token as password) -- never logged, never included in a
return value, and never echoed back in error messages.

Every command that sends a real message or call, or deprovisions a number,
is gated by RailCall's airlock: preview -> approve -> execute. Read-only
lookups run instantly. Handler functions return (output, artifact) tuples,
never a bare dict -- the loader unpacks two values.
"""

import os

import requests

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


def _request(method: str, path: str, *, params: dict = None, data: dict = None) -> dict:
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


def _require(inputs: dict, field: str) -> str:
    value = inputs.get(field)
    if not value:
        raise ValueError(f"'{field}' is required and was not provided.")
    return value


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

    body = _request("GET", "/Messages.json", params=params)
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
    m = _request("GET", f"/Messages/{message_sid}.json")
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

    body = _request("GET", "/Messages.json", params=params)
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

    body = _request("GET", "/Calls.json", params=params)
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
    balance = _request("GET", "/Balance.json")
    usage_body = _request("GET", "/Usage/Records/ThisMonth.json")

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
    m = _request("POST", "/Messages.json", data=data)
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
    c = _request("POST", "/Calls.json", data=data)
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
            m = _request("POST", "/Messages.json", data={"To": to, "From": from_, "Body": body_text})
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

    m = _request("POST", "/Messages.json", data={"To": to, "From": from_, "Body": rendered})
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
    _request("DELETE", f"/IncomingPhoneNumbers/{phone_number_sid}.json")
    return {
        "phone_number_sid": phone_number_sid,
        "status": "released",
    }, None
