"""Re-sign stripe-ops after any edit to module.json or handlers/handler.py.

Regenerates module.sig using this machine's local RailCall publisher key
(~/.railcall/marketplace_publisher.json, minted by `railcall market publisher
init`). Uses the exact same canonicalization the RailCall module loader
verifies against: canonical(module.json without "signature") + b"\\n" + handler.py bytes.

Usage: python3 sign_module.py
"""
import json, os
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLISHER_KEY_PATH = os.path.expanduser("~/.railcall/marketplace_publisher.json")

with open(PUBLISHER_KEY_PATH, encoding="utf-8") as f:
    rec = json.load(f)

with open(os.path.join(MODULE_DIR, "module.json"), encoding="utf-8") as f:
    manifest = json.load(f)

with open(os.path.join(MODULE_DIR, "handlers", "handler.py"), "rb") as f:
    handler_bytes = f.read()

m = {k: v for k, v in manifest.items() if k != "signature"}
canonical = json.dumps(m, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
payload = canonical + b"\n" + handler_bytes

priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(rec["seed_hex"]))
sig_hex = priv.sign(payload).hex()

sig_path = os.path.join(MODULE_DIR, "module.sig")
with open(sig_path, "w", encoding="utf-8") as f:
    f.write(sig_hex)

ok = manifest.get("publisher_pubkey") == rec["pubkey_hex"]
print("publisher_pubkey match:", ok)
if not ok:
    print("  WARNING: module.json's publisher_pubkey doesn't match your local key.")
    print("  local key pubkey:", rec["pubkey_hex"])
print("module.sig written:", sig_path)
