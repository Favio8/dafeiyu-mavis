"""Exercise the worker parser with private in-memory streams; no code deserialization."""
import io
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

from assistant import worker
from assistant.ipc import Message, ProtocolError, decode, encode


@pytest.mark.parametrize("kind,code", [("ping", 0), ("stop", 0), ("crash", 17)])
def test_worker_closed_command_loop(monkeypatch, kind, code):
    identity = dict(session="b" * 64, task_id=uuid4(), generation=1, role="host")
    data = encode(Message(**identity, seq=1, kind="hello")) + encode(Message(**identity, seq=2, kind=kind))
    output = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(data)))
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=output))
    monkeypatch.setattr(sys, "argv", ["worker", "--test-mode"])
    assert worker.main() == code
    assert decode(output.getvalue().splitlines(keepends=True)[0]).kind == "ready"


def test_worker_will_not_hang_in_live_mode(monkeypatch):
    identity = dict(session="b" * 64, task_id=uuid4(), generation=1, role="host")
    data = encode(Message(**identity, seq=1, kind="hello")) + encode(Message(**identity, seq=2, kind="hang"))
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(data)))
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=io.BytesIO()))
    monkeypatch.setattr(sys, "argv", ["worker"])
    with pytest.raises(ProtocolError):
        worker.main()
