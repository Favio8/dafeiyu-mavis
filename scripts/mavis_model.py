"""Local secure credential setup and separate small, explicitly requested API probes."""
import argparse
import asyncio
import getpass
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assistant.credentials import Credentials, CredentialUnavailable
from assistant.provider import DeepSeekProvider, ProviderSettings, ProviderError


def main() -> int:
    """Never accept a key in argv, files or stdout. Probe output contains no response body."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--save-key", action="store_true")
    parser.add_argument("--probe", choices=["connection", "tools"])
    parser.add_argument("--model", default="deepseek-flash")
    args = parser.parse_args()
    vault = Credentials()
    if args.save_key:
        if not sys.stdin.isatty():
            raise SystemExit("Run in your local interactive terminal; redirected key input is refused.")
        key = getpass.getpass("DeepSeek API Key (hidden): ")
        vault.save("deepseek/default", key)
        del key
        print("Credential saved in Windows Credential Manager; connection not yet tested.")
    if args.probe:
        secret = vault.read("deepseek/default")
        if not secret:
            print(json.dumps({"status": "not_run", "reason": "CREDENTIAL_MISSING"}))
            return 2
        client = DeepSeekProvider(ProviderSettings(model=args.model), secret)
        tools = []
        choice = "auto"
        if args.probe == "tools":
            tools = [{"type": "function", "function": {"name": "probe_echo", "description": "Return a probe marker; no side effect.",
                "parameters": {"type": "object", "properties": {"marker": {"type": "string", "enum": ["mavis"]}},
                               "required": ["marker"], "additionalProperties": False}}}]
            choice = {"type": "function", "function": {"name": "probe_echo"}}
        result = asyncio.run(client.complete([{"role": "user", "content": "Return the marker mavis."}], tools, threading.Event(), tool_choice=choice))
        passed = bool(result.message.get("content"))
        if args.probe == "tools":
            calls = result.message.get("tool_calls", [])
            passed = bool(calls and calls[0]["function"]["name"] == "probe_echo" and json.loads(calls[0]["function"]["arguments"]) == {"marker": "mavis"})
        print(json.dumps({"probe": args.probe, "model": args.model, "passed": passed,
                          "input_tokens": result.input_tokens, "output_tokens": result.output_tokens}))
        return 0 if passed else 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ProviderError, CredentialUnavailable) as exc:
        print(json.dumps({"status": "failed", "code": str(exc)}))
        raise SystemExit(1)
