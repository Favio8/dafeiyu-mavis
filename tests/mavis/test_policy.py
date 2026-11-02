"""Local policy never accepts model risk labels or a page's purported permission."""
import os
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from assistant.actions import ACTION_SCHEMA, Click, CreateFile, FixtureAction, OpenURL, Shortcut, TypeText
from assistant.contracts import Observation
from assistant.policy import Policy, PolicyDenied, Scope, digest, normalize_url, new_file_path


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///C:/Windows", "data:text/html,x", "ms-settings:privacy",
    "http://example.com", "https://user:pass@example.com", "https://example.com\\@evil.com", "https://example.com:444/",
    "https://example.com./", "https://example.com/%0afoo", " https://example.com", "https://example.com#evil"])
def test_dangerous_urls(url):
    with pytest.raises(PolicyDenied):
        normalize_url(url)


def test_exact_domain_and_canonical_https():
    assert normalize_url("HTTPS://EXAMPLE.COM:443") == "https://example.com/"
    p = Policy(Scope(enabled=True, apps=frozenset({"msedge.exe"}), domains=frozenset({"example.com"})))
    observation = Observation(captured_mono=10.0, context_digest="a" * 64, hwnd=1, pid=999999, app="msedge.exe", integrity="medium")
    for url in ["https://evil.example.com/", "https://example.com.evil.com/"]:
        with pytest.raises(PolicyDenied):
            p.evaluate(OpenURL(task_id=uuid4(), generation=1, url=url), observation, mode="live", now=10, max_age_ms=2000)


@pytest.mark.parametrize("field,value", [("app", "powershell.exe"), ("app", "cmd.exe"), ("app", "run"),
    ("integrity", "high"), ("integrity", "unknown"), ("own_ui", True), ("pid", os.getpid()), ("hwnd", 0)])
def test_unsafe_windows(field, value):
    observation = Observation(captured_mono=10.0, context_digest="a" * 64, hwnd=1, pid=999999, app="notepad.exe", integrity="medium", safe_control=True, control_id="ok")
    policy = Policy(Scope(enabled=True, apps=frozenset({"notepad.exe", "powershell.exe", "cmd.exe", "run"})))
    with pytest.raises(PolicyDenied):
        policy.evaluate(Click(task_id=uuid4(), generation=1, control_id="ok"), observation.model_copy(update={field: value}), mode="live", now=10, max_age_ms=2000)


@pytest.mark.parametrize("keys", ["win+r", "ctrl+shift+enter", "enter", "alt+f4", "ctrl+s", "ctrl+v", "win", "shift+delete"])
def test_shortcut_bypass(keys):
    observation = Observation(captured_mono=10.0, context_digest="a" * 64, hwnd=1, pid=999999, app="notepad.exe", integrity="medium", editable_draft=True)
    with pytest.raises(PolicyDenied):
        Policy(Scope(enabled=True, apps=frozenset({"notepad.exe"}))).evaluate(
            Shortcut(task_id=uuid4(), generation=1, keys=keys), observation, mode="live", now=10, max_age_ms=2000)


def test_schema_cannot_grant_risk_or_execute_shell():
    for payload in [dict(tool="shell_tool", command="forbidden"), dict(tool="fixture.increment", risk="R0"), dict(tool="file.delete", path="x")]:
        with pytest.raises(ValidationError):
            ACTION_SCHEMA.validate_python(dict(task_id=uuid4(), generation=1, **payload))


def test_path_existing_traversal_ads_and_reserved(tmp_path):
    existing = tmp_path / "existing.txt"
    existing.write_text("untouched")
    for path in [existing, tmp_path / ".." / "escape.txt", tmp_path / "x.txt:stream", tmp_path / "NUL.txt", tmp_path / "bad. "]:
        with pytest.raises(PolicyDenied):
            new_file_path(str(path), (tmp_path,))
    assert new_file_path(str(tmp_path / "new.txt"), (tmp_path,)) == tmp_path / "new.txt"
    assert existing.read_text() == "untouched"
    assert not (tmp_path / "new.txt").exists()


def test_outside_root_and_symlink(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(PolicyDenied):
        new_file_path(str(tmp_path / "escape.txt"), (root,))
    link = root / "linked"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("this Windows account cannot create symlinks; reparse real-machine test remains pending")
    with pytest.raises(PolicyDenied):
        new_file_path(str(link / "escape.txt"), (root,))


def test_live_mode_cannot_execute_fixture():
    with pytest.raises(PolicyDenied, match="TEST_ONLY"):
        Policy().evaluate(FixtureAction(task_id=uuid4(), generation=1), Observation(captured_mono=1.0, context_digest=digest({}), app="mavis.fixture"), mode="live", now=1, max_age_ms=2000)
