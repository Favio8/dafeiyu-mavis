"""Bounded DeepSeek HTTP client. No SDK auto-telemetry, redirects or plaintext keys."""
from __future__ import annotations

import asyncio
import json
import threading
import random
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import aiohttp
from pydantic import Field, field_validator

from .contracts import Record

MAX_RESPONSE = 262144


class ProviderError(RuntimeError):
    """Only a stable, non-secret error code may escape the HTTP layer."""


class ProviderSettings(Record):
    """Local configuration, never accepted from model or desktop content."""
    base_url: str = "https://api.deepseek.com"
    model: str = Field(default="deepseek-flash", min_length=1, max_length=120)
    timeout_s: int = Field(default=45, ge=10, le=120)
    retries: int = Field(default=2, ge=0, le=2)

    @field_validator("base_url")
    @classmethod
    def official_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.netloc != "api.deepseek.com" or parsed.path not in ("", "/", "/v1", "/v1/") or parsed.query or parsed.fragment:
            raise ValueError("only the official DeepSeek HTTPS origin is supported")
        return value.rstrip("/")


@dataclass(frozen=True)
class Completion:
    """Response data only; tool calls are proposals, never permission or success."""
    message: dict
    input_tokens: int | None
    output_tokens: int | None


def parse_completion(data: dict) -> Completion:
    """Validate remote structure and preserve missing usage as unknown."""
    try:
        choices = data["choices"]
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError
        message = choices[0]["message"]
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise ValueError
        text = message.get("content")
        if text is not None and (not isinstance(text, str) or len(text) > 16000):
            raise ValueError
        calls = message.get("tool_calls") or []
        if not isinstance(calls, list) or len(calls) > 1:
            raise ValueError
        for call in calls:
            if not isinstance(call, dict) or call.get("type") != "function":
                raise ValueError
            function = call["function"]
            if not isinstance(call["id"], str) or not 1 <= len(call["id"]) <= 128:
                raise ValueError
            if not isinstance(function["name"], str) or not 1 <= len(function["name"]) <= 80:
                raise ValueError
            if not isinstance(function["arguments"], str) or len(function["arguments"]) > 16000:
                raise ValueError
        usage = data.get("usage") or {}
        if not isinstance(usage, dict):
            raise ValueError
        tokens = [usage.get("prompt_tokens"), usage.get("completion_tokens")]
        if any(v is not None and (type(v) is not int or v < 0) for v in tokens):
            raise ValueError
        # Do not carry unexpected remote fields into later requests.
        clean = {"role": "assistant", "content": text}
        if calls:
            clean["tool_calls"] = calls
        return Completion(clean, *tokens)
    except (KeyError, TypeError, ValueError):
        raise ProviderError("INVALID_PROVIDER_RESPONSE") from None


class DeepSeekProvider:
    """Keys remain in memory; cancellation closes the in-flight aiohttp request."""
    def __init__(self, settings: ProviderSettings, secret: str):
        if not secret or len(secret) > 1024 or any(c.isspace() for c in secret):
            raise ProviderError("INVALID_CREDENTIAL")
        self.settings, self._secret = settings, secret

    async def _request(self, body: dict) -> dict:
        timeout = aiohttp.ClientTimeout(total=self.settings.timeout_s, connect=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
                async with session.post(self.settings.base_url + "/chat/completions", json=body,
                    headers={"Authorization": "Bearer " + self._secret}, allow_redirects=False) as response:
                    if response.status != 200:
                        codes = {401: "AUTH_FAILED", 403: "AUTH_FAILED", 402: "QUOTA_EXHAUSTED", 429: "RATE_LIMITED"}
                        if 300 <= response.status < 400:
                            raise ProviderError("REDIRECT_REFUSED")
                        raise ProviderError(codes.get(response.status, "SERVER_ERROR" if response.status >= 500 else "REQUEST_REJECTED"))
                    raw = bytearray()
                    async for chunk in response.content.iter_chunked(8192):
                        raw.extend(chunk)
                        if len(raw) > MAX_RESPONSE:
                            raise ProviderError("RESPONSE_TOO_LARGE")
                    result = json.loads(raw)
                    if not isinstance(result, dict):
                        raise ProviderError("INVALID_PROVIDER_RESPONSE")
                    return result
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            raise ProviderError("MODEL_TIMEOUT") from None
        except aiohttp.ClientConnectionError:
            raise ProviderError("NETWORK_UNAVAILABLE") from None
        except (aiohttp.ClientError, UnicodeError, ValueError):
            raise ProviderError("INVALID_PROVIDER_RESPONSE") from None

    async def complete(self, messages: list[dict], tools: list[dict], stop: threading.Event,
                       *, tool_choice: Any = "auto") -> Completion:
        """Retry only model requests (bounded); never retry tool side effects here."""
        if len(json.dumps(messages, ensure_ascii=False)) > 64000:
            raise ProviderError("CONTEXT_TOO_LARGE")
        body = {"model": self.settings.model, "messages": messages, "stream": False,
                "max_tokens": 2048, "thinking": {"type": "disabled"}}
        if tools:
            body.update(tools=tools, tool_choice=tool_choice)
        deadline = asyncio.get_running_loop().time() + self.settings.timeout_s
        for attempt in range(self.settings.retries + 1):
            if stop.is_set():
                raise ProviderError("CANCELLED")
            request = asyncio.create_task(self._request(body))
            try:
                while not request.done():
                    if stop.is_set():
                        raise ProviderError("CANCELLED")
                    if asyncio.get_running_loop().time() >= deadline:
                        raise ProviderError("MODEL_TIMEOUT")
                    await asyncio.wait({request}, timeout=0.05)
                if stop.is_set():
                    raise ProviderError("CANCELLED")
                return parse_completion(await request)
            except ProviderError as exc:
                if str(exc) not in {"RATE_LIMITED", "SERVER_ERROR", "NETWORK_UNAVAILABLE"} or attempt >= self.settings.retries:
                    raise
                until = min(deadline, asyncio.get_running_loop().time() + .25 * 2**attempt + random.uniform(0,.10))
                while asyncio.get_running_loop().time() < until:
                    if stop.is_set():
                        raise ProviderError("CANCELLED")
                    await asyncio.sleep(.025)
            finally:
                if not request.done():
                    request.cancel()
                await asyncio.gather(request, return_exceptions=True)
        raise ProviderError("RETRY_EXHAUSTED")
