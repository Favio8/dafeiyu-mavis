"""Separate connection/tool probes; never create successful user tasks or enable input."""
import json
import threading

from .provider import DeepSeekProvider, ProviderError


async def probe(client: DeepSeekProvider, kind: str, stop: threading.Event) -> dict:
    """Send a fixed non-private marker. No user screen, command or document is sent."""
    if kind not in {"connection", "tools"}:
        raise ValueError("unsupported model diagnostic")
    tools, choice = [], "auto"
    if kind == "tools":
        tools = [{"type": "function", "function": {"name": "probe_echo", "description": "Echo a marker; no side effect.",
            "parameters": {"type": "object", "properties": {"marker": {"type": "string", "enum": ["mavis"]}},
                           "required": ["marker"], "additionalProperties": False}}}]
        choice = {"type": "function", "function": {"name": "probe_echo"}}
    result = await client.complete([{"role": "user", "content": "Return the marker mavis."}], tools, stop, tool_choice=choice)
    passed = bool(result.message.get("content"))
    if kind == "tools":
        calls = result.message.get("tool_calls", [])
        try:
            passed = bool(calls and calls[0]["function"]["name"] == "probe_echo" and json.loads(calls[0]["function"]["arguments"]) == {"marker": "mavis"})
        except (ValueError, KeyError, TypeError):
            raise ProviderError("INVALID_TOOL_PROBE_RESPONSE") from None
    return {"probe": kind, "model": client.settings.model, "passed": passed,
            "input_tokens": result.input_tokens, "output_tokens": result.output_tokens}
