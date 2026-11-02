"""Real cross-process vault probe using a random disposable marker, never an API Key."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
from uuid import uuid4

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assistant.credentials import Credentials


def main() -> int:
    """Write/read/delete only a unique probe credential, including when frozen."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--read-ref")
    args = parser.parse_args()
    vault = Credentials()
    if args.read_ref:
        value = vault.read(args.read_ref)
        print(hashlib.sha256(value.encode()).hexdigest() if value else "missing")
        return 0 if value else 1
    ref, marker = "probe/" + uuid4().hex, secrets.token_urlsafe(24)
    vault.save(ref, marker)
    try:
        command = [sys.executable]
        if not getattr(sys, "frozen", False):
            command.append(str(Path(__file__).resolve()))
        command += ["--read-ref", ref]
        result = subprocess.run(command, capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        passed = result.returncode == 0 and result.stdout.strip() == hashlib.sha256(marker.encode()).hexdigest()
    finally:
        vault.delete(ref)
    absent = vault.read(ref) is None
    print(json.dumps({"backend": type(vault.backend).__name__, "frozen": bool(getattr(sys, "frozen", False)),
                      "cross_process_roundtrip": passed, "probe_removed": absent}))
    return 0 if passed and absent else 1


if __name__ == "__main__":
    raise SystemExit(main())
