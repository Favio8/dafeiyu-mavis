"""Positive scopes stay narrow, and semantic uncertainty always stops the action."""
from uuid import uuid4

import pytest

from assistant.actions import Click, CreateFile, LaunchApp, OpenURL, Scroll, Shortcut, TypeText
from assistant.contracts import Observation
from assistant.policy import Policy, PolicyDenied, Scope


def test_normalized_scoped_actions_and_semantics(tmp_path):
    policy = Policy(Scope(enabled=True, apps=frozenset({"notepad.exe"}), domains=frozenset({"example.com"}), folders=(tmp_path,)))
    identity = dict(task_id=uuid4(), generation=1)
    observation = Observation(captured_mono=10.0, context_digest="a" * 64, hwnd=1, pid=999999,
        app="notepad.exe", integrity="medium", control_id="draft", editable_draft=True, safe_control=True)
    actions = [LaunchApp(**identity, app_id="notepad.exe"), OpenURL(**identity, url="HTTPS://EXAMPLE.COM/"),
        CreateFile(**identity, path=str(tmp_path / "new.txt"), content="draft"),
        Click(**identity, control_id="draft"), TypeText(**identity, control_id="draft", text="中文 draft"),
        Scroll(**identity, direction="down", ticks=1), Shortcut(**identity, keys="CTRL+A")]
    for action in actions:
        normalized, risk = policy.evaluate(action, observation, mode="live", now=10.0, max_age_ms=2000)
        assert risk == ("R1" if isinstance(action, CreateFile) else "R0")
    assert not (tmp_path / "new.txt").exists()
    unsafe = [LaunchApp(**identity, app_id="cmd.exe"), TypeText(**identity, control_id="unknown", text="x"),
              TypeText(**identity, control_id="draft", text="hello\nsubmit")]
    for action in unsafe:
        with pytest.raises(PolicyDenied):
            policy.evaluate(action, observation, mode="live", now=10.0, max_age_ms=2000)
    for action in [Click(**identity, control_id="draft"), Scroll(**identity, direction="down", ticks=1)]:
        with pytest.raises(PolicyDenied):
            policy.evaluate(action, observation.model_copy(update={"safe_control": False}), mode="live", now=10.0, max_age_ms=2000)
    for altered in [observation.model_copy(update={"domain": "evil.com"}), observation.model_copy(update={"captured_mono": 0.0})]:
        with pytest.raises(PolicyDenied):
            policy.evaluate(actions[-1], altered, mode="live", now=10.0, max_age_ms=2000)
    with pytest.raises(PolicyDenied, match="DISABLED"):
        Policy().evaluate(actions[0], observation, mode="live", now=10.0, max_age_ms=2000)
