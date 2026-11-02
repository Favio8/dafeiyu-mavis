"""Native input boundary tests with an inert SendInput sink; real GUI probes are separate."""
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from assistant.actions import TypeText, FocusWindow
from assistant.contracts import Observation
from assistant.notepad_backend import NotepadDraftBackend
from assistant.policy import Policy, PolicyDenied, Scope


def build(monkeypatch):
    import win32gui
    node = NotepadDraftBackend.__new__(NotepadDraftBackend)
    obs = Observation(captured_mono=time.monotonic(), context_digest="a"*64, hwnd=123, pid=9999, app="notepad.exe", integrity="medium", control_id="draft", editable_draft=True)
    node.target = node.expected = obs
    node.lease = SimpleNamespace(handle=1, owner=threading.get_ident())
    node.hotkey = SimpleNamespace(registered=True)
    node.stop = threading.Event()
    node.goal_text, node.prefix = "你", ""
    calls = []
    body = [""]
    def send(count, inputs, size):
        calls.append((count, size))
        body[0] = "你"
        return count
    node.user = SimpleNamespace(GetAsyncKeyState=lambda key:0, SendInput=send)
    node.observe_draft = lambda **kwargs:obs
    node.read_text = lambda:body[0]
    monkeypatch.setattr(win32gui, "GetForegroundWindow", lambda:obs.hwnd)
    action = TypeText(task_id=uuid4(), generation=1, control_id="draft", text="你")
    return node, action, calls


@pytest.mark.parametrize("fault", ["stop", "lease", "hotkey", "context", "goal", "modifier", "foreground"])
def test_deny_before_any_input(monkeypatch, fault):
    node, action, calls = build(monkeypatch)
    if fault == "stop": node.stop.set()
    elif fault == "lease": node.lease.handle = None
    elif fault == "hotkey": node.hotkey.registered = False
    elif fault == "context": node.expected = node.expected.model_copy(update={"context_digest":"b"*64})
    elif fault == "goal": action = action.model_copy(update={"text":"他"})
    elif fault == "modifier": node.user.GetAsyncKeyState = lambda key:0x8000
    elif fault == "foreground":
        import win32gui
        monkeypatch.setattr(win32gui,"GetForegroundWindow",lambda:456)
    with pytest.raises(PolicyDenied):
        node.execute(action, node.stop)
    assert calls == []


def test_one_scalar_and_partial_send_release(monkeypatch):
    node, action, calls = build(monkeypatch)
    node.execute(action, node.stop)
    assert len(calls) == 1 and calls[0][0] == 2 and node.prefix == "你"
    node, action, calls = build(monkeypatch)
    def partial(count, inputs, size):
        calls.append(count)
        return 1
    node.user.SendInput = partial
    with pytest.raises(RuntimeError, match="PARTIAL_UNICODE_INPUT"):
        node.execute(action, node.stop)
    assert calls == [2, 1] and node.stop.is_set()


def test_focus_is_bound_to_observed_window():
    policy = Policy(Scope(enabled=True, apps=frozenset({"notepad.exe"})))
    obs = Observation(captured_mono=1.0, context_digest="a"*64, hwnd=123, pid=9999, app="notepad.exe", integrity="medium")
    with pytest.raises(PolicyDenied):
        policy.evaluate(FocusWindow(task_id=uuid4(),generation=1,hwnd=456),obs,mode="live",now=1.0,max_age_ms=2000)
