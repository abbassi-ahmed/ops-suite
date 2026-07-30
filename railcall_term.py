#!/usr/bin/env python3
"""Terminal client for RailCall modules — no browser, no custom control panel.

Drives the exact same Studio HTTP API the browser UI uses
(/api/commands/preview -> approve -> execute on 127.0.0.1:8799), but from
a plain terminal command. Approval uses method="terminal_confirm" (a peer
to the UI's "ui_click" in RailCall's own airlock), so a write command's
preview -> human-approve -> execute -> signed-receipt cycle runs entirely
in the terminal.

Usage:
    python3 railcall_term.py <module>.<command> [--field=value ...]

Examples:
    python3 railcall_term.py ops-suite.list_charges --limit=5
    python3 railcall_term.py ops-suite.create_refund --charge_id=py_3N... --reason=requested_by_customer

<module> may be a bare module id (e.g. "ops-suite") or a full slug
(e.g. "abbassi-ahmed/ops-suite") — only the last path segment is used to
find the deployed module's manifest under
~/.railcall/station/modules/<module>/module.json (used locally to know
each field's declared type, so e.g. --limit=5 is sent as a number, not a
string — RailCall's own validator rejects a numeric field sent as a
string).
"""

import json
import os
import sys
import urllib.error
import urllib.request

RAILCALL_BASE = "http://127.0.0.1:8799"
SESSION_TOKEN_PATH = os.path.expanduser(
    "~/.railcall/station/.railcall_workspace/session_token"
)
MODULES_DIR = os.path.expanduser("~/.railcall/station/modules")


def _fail(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def _read_session_token():
    try:
        with open(SESSION_TOKEN_PATH) as f:
            return f.read().strip()
    except OSError:
        _fail(
            "couldn't read the Studio session token at "
            f"{SESSION_TOKEN_PATH} — is `railcall studio` running?"
        )


def _load_command_schema(module_ref, command_id):
    module_id = module_ref.rstrip("/").split("/")[-1]
    manifest_path = os.path.join(MODULES_DIR, module_id, "module.json")
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except OSError:
        _fail(
            f"no deployed module found at {manifest_path} — is "
            f"'{module_id}' installed/deployed under ~/.railcall/station/modules/?"
        )
    for cmd in manifest.get("commands", []):
        if cmd.get("id") == command_id:
            return cmd
    _fail(f"command '{command_id}' not found in {module_id}'s module.json")


def _parse_cli_inputs(argv, input_schema):
    inputs = {}
    for arg in argv:
        if not arg.startswith("--") or "=" not in arg:
            _fail(f"unrecognized argument '{arg}' (expected --field=value)")
        field, raw_value = arg[2:].split("=", 1)
        field_type = (input_schema.get(field) or {}).get("type")
        if field_type == "number":
            try:
                value = int(raw_value)
            except ValueError:
                try:
                    value = float(raw_value)
                except ValueError:
                    _fail(f"--{field} must be a number, got '{raw_value}'")
        elif field_type in ("array", "object"):
            try:
                value = json.loads(raw_value)
            except ValueError:
                _fail(f"--{field} must be valid JSON ({field_type}), got '{raw_value}'")
        else:
            value = raw_value
        inputs[field] = value
    return inputs


def _api_call(path, body, session_token):
    req = urllib.request.Request(
        f"{RAILCALL_BASE}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-RailCall-Session": session_token,
            "Origin": RAILCALL_BASE,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except ValueError:
            _fail(f"{path} -> HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        _fail(
            f"couldn't reach {RAILCALL_BASE}{path} ({e.reason}) — "
            "is `railcall studio` running?"
        )


def main():
    if len(sys.argv) < 2 or "." not in sys.argv[1]:
        _fail("usage: railcall_term.py <module>.<command> [--field=value ...]")

    module_ref, command_id = sys.argv[1].rsplit(".", 1)
    cmd_schema = _load_command_schema(module_ref, command_id)
    input_schema = cmd_schema.get("input_schema") or {}
    inputs = _parse_cli_inputs(sys.argv[2:], input_schema)

    session_token = _read_session_token()
    intent = f"railcall_term.py: {' '.join(sys.argv[1:])}"

    preview = _api_call(
        "/api/commands/preview",
        {"command_id": command_id, "inputs": inputs, "intent": intent},
        session_token,
    )
    if not preview.get("ok"):
        print(json.dumps(preview, indent=2))
        sys.exit(1)

    card = preview.get("card", {})
    print(json.dumps(card, indent=2))

    if not preview.get("requires_approval"):
        # Read command — preview never calls the handler, so we still need
        # execute() to actually run it and get real data back.
        result = _api_call(
            "/api/commands/execute",
            {"command_id": command_id, "inputs": inputs, "intent": intent},
            session_token,
        )
        print(json.dumps(result, indent=2))
        return

    answer = input("\nApprove and execute the above? [y/N] ").strip().lower()
    if answer != "y":
        print("Not approved — nothing executed.")
        return

    approval = _api_call(
        "/api/commands/approve",
        {
            "command_id": command_id,
            "inputs": inputs,
            "method": "terminal_confirm",
            "intent": intent,
        },
        session_token,
    )
    if not approval.get("ok"):
        print(json.dumps(approval, indent=2))
        sys.exit(1)

    result = _api_call(
        "/api/commands/execute",
        {"command_id": command_id, "inputs": inputs, "intent": intent},
        session_token,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
