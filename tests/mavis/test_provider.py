"""API contract/transport safety; no fixture is counted as a live provider test."""
import asyncio
import json
import threading

import pytest
from pydantic import ValidationError

from assistant.provider import DeepSeekProvider, ProviderError, ProviderSettings, parse_completion


def response(text="done", usage=None):
    return {"choices": [{"message": {"role": "assistant", "content": text}}], "usage": usage}


@pytest.mark.parametrize("url", ["http://api.deepseek.com", "https://api.deepseek.com.evil.com", "https://user:pass@api.deepseek.com", "https://api.deepseek.com/path?token=x"])
def test_official_tls_origin_only(url):
    with pytest.raises(ValidationError):
        ProviderSettings(base_url=url)


def test_unknown_metrics_and_response_schema():
    result = parse_completion(response())
    assert result.input_tokens is None and result.output_tokens is None
    assert parse_completion(response(usage={"prompt_tokens": 3, "completion_tokens": 4})).input_tokens == 3
    for value in [{}, response(text={}), response(usage={"prompt_tokens": True}), {"choices": []}]:
        with pytest.raises(ProviderError):
            parse_completion(value)


def test_cancel_closes_inflight_request(monkeypatch):
    async def scenario():
        stop, entered, closed = threading.Event(), asyncio.Event(), asyncio.Event()
        client = DeepSeekProvider(ProviderSettings(), "test-marker")
        async def hanging(body):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                closed.set()
        monkeypatch.setattr(client, "_request", hanging)
        task = asyncio.create_task(client.complete([{"role":"user","content":"test"}], [], stop))
        await asyncio.wait_for(entered.wait(), 2)
        stop.set()
        with pytest.raises(ProviderError, match="CANCELLED"):
            await asyncio.wait_for(task, 2)
        assert closed.is_set()
    asyncio.run(scenario())


def test_retries_only_retryable_http_errors(monkeypatch):
    client = DeepSeekProvider(ProviderSettings(retries=1), "test-marker")
    calls = []
    async def request(body):
        calls.append(body)
        raise ProviderError("RATE_LIMITED")
    monkeypatch.setattr(client, "_request", request)
    with pytest.raises(ProviderError, match="RATE_LIMITED"):
        asyncio.run(client.complete([{"role":"user","content":"test"}], [], threading.Event()))
    assert len(calls) == 2
    calls.clear()
    async def auth(body):
        calls.append(body)
        raise ProviderError("AUTH_FAILED")
    monkeypatch.setattr(client, "_request", auth)
    with pytest.raises(ProviderError, match="AUTH_FAILED"):
        asyncio.run(client.complete([{"role":"user","content":"test"}], [], threading.Event()))
    assert len(calls) == 1


@pytest.mark.parametrize("status,code", [(302,"REDIRECT_REFUSED"),(401,"AUTH_FAILED"),(402,"QUOTA_EXHAUSTED"),(429,"RATE_LIMITED"),(500,"SERVER_ERROR")])
def test_transport_never_follows_redirect_or_returns_error_body(monkeypatch, status, code):
    from assistant import provider
    captured = []
    class Response:
        async def __aenter__(self):
            self.status = status
            return self
        async def __aexit__(self, *args):
            pass
    class Session:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        def post(self, url, **kwargs):
            captured.append((url, kwargs))
            return Response()
    monkeypatch.setattr(provider.aiohttp, "ClientSession", Session)
    client = DeepSeekProvider(ProviderSettings(retries=0), "private-test-marker")
    with pytest.raises(ProviderError, match="^" + code + "$"):
        asyncio.run(client.complete([{"role":"user","content":"test"}], [], threading.Event()))
    assert captured[0][1]["allow_redirects"] is False
    assert captured[0][0] == "https://api.deepseek.com/chat/completions"
    assert "private-test-marker" not in repr(client)


def test_context_limit_precedes_network(monkeypatch):
    client = DeepSeekProvider(ProviderSettings(), "marker")
    with pytest.raises(ProviderError, match="CONTEXT_TOO_LARGE"):
        asyncio.run(client.complete([{"role":"user","content":"a" * 65000}], [], threading.Event()))
