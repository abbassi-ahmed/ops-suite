#!/usr/bin/env python3
"""Personal control panel for the stripe-ops RailCall module.

This is NOT part of the marketplace module (RailCall modules can only be
module.json + handlers/handler.py + module.sig). It's a standalone local
tool: a small HTTP server that serves a nicer UI and proxies API calls to
the real RailCall Studio server running on 127.0.0.1:8799, so the browser
only ever talks to THIS server (same-origin, no CORS/CSRF headaches) and
every real action still goes through RailCall's actual preview -> approve
-> execute airlock and signed receipts. Nothing here bypasses RailCall's
safety checks; it's a friendlier front door to the same real API.

Run:  python3 server.py
Then open http://127.0.0.1:8900
Requires the real RailCall Studio server to already be running on :8799
with STRIPE_SECRET_KEY set in ITS environment.
"""
import json
import os
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RAILCALL_BASE = "http://127.0.0.1:8799"
SESSION_TOKEN_PATH = os.path.expanduser(
    "~/.railcall/station/.railcall_workspace/session_token"
)
RECEIPTS_DIR = os.path.expanduser(
    "~/.railcall/station/.railcall_workspace/receipts"
)
MODULE_JSON_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "module.json")
PORT = 8900

with open(MODULE_JSON_PATH, encoding="utf-8") as f:
    _MANIFEST = json.load(f)
OUR_COMMAND_IDS = {c["id"] for c in _MANIFEST.get("commands", [])}


def _session_token():
    try:
        with open(SESSION_TOKEN_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def _railcall_request(method, path, body=None):
    """Server-to-server call to the real RailCall API. Not subject to browser
    CORS at all since the browser never talks to :8799 directly."""
    tok = _session_token()
    if not tok:
        return 503, {"ok": False, "error": "RailCall Studio server isn't running (no session token found). Start it first."}
    headers = {
        "Content-Type": "application/json",
        "X-RailCall-Session": tok,
        "Origin": RAILCALL_BASE,
        "Referer": RAILCALL_BASE + "/v2",
    }
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(RAILCALL_BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"ok": False, "error": str(e)}
    except Exception as e:
        return 502, {"ok": False, "error": f"couldn't reach RailCall Studio on :8799 ({type(e).__name__}: {e})"}


def _recent_receipts(limit=15):
    if not os.path.isdir(RECEIPTS_DIR):
        return []
    files = sorted(
        (f for f in os.listdir(RECEIPTS_DIR) if f.endswith(".json")),
        reverse=True,
    )[:limit]
    out = []
    for fn in files:
        try:
            with open(os.path.join(RECEIPTS_DIR, fn), encoding="utf-8") as f:
                rc = json.load(f)
        except Exception:
            continue
        if rc.get("resolved_command_id") not in OUR_COMMAND_IDS:
            continue
        out.append({
            "receipt_id": rc.get("receipt_id") or fn,
            "command_id": rc.get("resolved_command_id"),
            "timestamp": rc.get("timestamp"),
            "result_status": rc.get("result_status"),
            "output": rc.get("output"),
            "note": rc.get("note"),
            "signed": bool(rc.get("signature")),
        })
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode())
        except Exception:
            return {}

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
            with open(index_path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/commands":
            status, data = _railcall_request("GET", "/api/commands/list")
            cmds = [c for c in (data.get("commands") or []) if c.get("id") in OUR_COMMAND_IDS]
            cmds.sort(key=lambda c: (c.get("mode") is None, c.get("id")))
            self._send_json(200, {"ok": True, "commands": cmds, "server_reachable": status != 503})
            return
        if self.path == "/api/receipts":
            self._send_json(200, {"ok": True, "receipts": _recent_receipts()})
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        route_map = {
            "/api/preview": "/api/commands/preview",
            "/api/approve": "/api/commands/approve",
            "/api/execute": "/api/commands/execute",
        }
        target = route_map.get(self.path)
        if not target:
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        body = self._read_body()
        if body.get("command_id") not in OUR_COMMAND_IDS:
            self._send_json(400, {"ok": False, "error": "unknown command_id for this panel"})
            return
        status, data = _railcall_request("POST", target, body)
        self._send_json(status if status else 200, data)


def main():
    print(f"stripe-ops control panel -> http://127.0.0.1:{PORT}")
    print(f"proxying to RailCall Studio at {RAILCALL_BASE}")
    if not _session_token():
        print("  (heads up: RailCall Studio doesn't look like it's running yet on :8799 --"
              " start it first, or this panel will show connection errors)")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    srv.serve_forever()


if __name__ == "__main__":
    main()
