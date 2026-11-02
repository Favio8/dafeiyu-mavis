"""Postconditions and native leases cannot be replaced by tool/model success text."""
import threading
from dataclasses import replace

import pytest

from assistant.contracts import Observation, Task
from assistant.policy import PolicyDenied
from assistant.stop import StopController
from assistant.verifier import Expected, verify_text, verify_url, verify_window
from assistant.visual_gate import VisualConsent, validate_visual_request
from assistant.windows_observer import ContextWatchdog, DesktopLease


def test_independent_postconditions():
    task = Task(original_text="test", final_text="test")
    expected = Expected("primary", "uia", "你好")
    assert verify_text(task, expected, None).result == "unknown"
    assert verify_text(task, expected, "different").result == "failed"
    assert verify_text(task, expected, "你好").result == "passed"
    assert "你好" not in verify_text(task, expected, "你好").evidence
    target = Expected("primary", "url", "https://www.bilibili.com/")
    assert verify_url(task, target, None).result == "unknown"
    assert verify_url(task, target, "https://evil.example/").result == "failed"
    assert verify_window(task, Expected("primary","window","notepad.exe"), None).result == "unknown"


def test_visual_gates_are_conjunctive():
    obs = Observation(captured_mono=1.0, context_digest="a"*64, integrity="medium", bounds=(-100,0,100,100))
    consent = VisualConsent(obs.context_digest, True, True, True)
    assert validate_visual_request(obs, consent, current_digest=obs.context_digest) == obs.bounds
    for field in ("screen_upload", "vision_verified", "low_risk_region_verified"):
        with pytest.raises(PolicyDenied):
            validate_visual_request(obs, replace(consent, **{field:False}), current_digest=obs.context_digest)
    with pytest.raises(PolicyDenied):
        validate_visual_request(obs, consent, current_digest="b"*64)


def test_context_loss_stops_independently():
    obs = Observation(captured_mono=1.0, context_digest="a"*64)
    stop = StopController()
    def changed(hwnd):
        return obs.model_copy(update={"context_digest":"b"*64})
    watcher = ContextWatchdog(obs, stop, changed)
    watcher.start()
    try:
        assert stop.event.wait(2)
    finally:
        watcher.close()


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows mutex")
def test_actual_session_mutex_rejects_recursive_ownership():
    one, two = DesktopLease(), DesktopLease()
    try:
        assert one.acquire()
        assert not two.acquire()
        one.close()
        assert two.acquire()
    finally:
        one.close()
        two.close()
