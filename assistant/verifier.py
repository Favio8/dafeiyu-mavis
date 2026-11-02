"""Independent postconditions. Model text and tool return values are not evidence."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import time
from pathlib import Path
from urllib.parse import urlsplit

from .contracts import Observation, Task, Verification
from .policy import normalize_url, PolicyDenied


@dataclass(frozen=True)
class Expected:
    """Host-defined immutable expectation, derived from the confirmed user goal."""
    goal_id: str
    method: str
    value: str
    hwnd: int | None = None
    pid: int | None = None
    identity_digest: str | None = None


def verify_window(task: Task, expected: Expected, actual: Observation | None) -> Verification:
    """Require a specific process/window and normal integrity, not an API return code."""
    matched = actual is not None and actual.app.casefold() == expected.value.casefold() and actual.integrity == "medium" and not actual.own_ui
    matched = matched and 0 <= time.monotonic()-actual.captured_mono <= task.budget.observation_ms/1000
    matched = matched and (expected.pid is None or actual.pid == expected.pid) and (expected.hwnd is None or actual.hwnd == expected.hwnd)
    matched = matched and (expected.identity_digest is None or actual.identity_digest == expected.identity_digest)
    return Verification(task_id=task.id, generation=task.generation, goal_id=expected.goal_id, method="window",
        result="passed" if matched else "unknown" if actual is None else "failed",
        evidence=f"window identity {'matched' if matched else 'not confirmed'}")


def verify_text(task: Task, expected: Expected, actual: str | None) -> Verification:
    """Compare text from an independent UIA read; persist hashes, not private document text."""
    matched = actual is not None and actual == expected.value
    evidence = "unavailable" if actual is None else "text_sha256=" + hashlib.sha256(actual.encode()).hexdigest()
    return Verification(task_id=task.id, generation=task.generation, goal_id=expected.goal_id, method="uia",
                        result="passed" if matched else "unknown" if actual is None else "failed", evidence=evidence)


def verify_url(task: Task, expected: Expected, actual_address: str | None) -> Verification:
    """Compare a separately observed browser address; launch success is insufficient."""
    result = "unknown"
    if actual_address is not None:
        try:
            result = "passed" if normalize_url(actual_address) == normalize_url(expected.value) else "failed"
        except PolicyDenied:
            result = "failed"
    return Verification(task_id=task.id, generation=task.generation, goal_id=expected.goal_id, method="url",
                        result=result, evidence="expected_host=" + (urlsplit(expected.value).hostname or "unknown"))


def verify_file(task: Task, expected: Expected, path: Path, authorized_root: Path) -> Verification:
    """Read only a bounded regular file beneath the host-approved test/work directory."""
    result, evidence = "unknown", "file unavailable"
    try:
        if path.is_symlink() or not path.resolve().is_relative_to(authorized_root.resolve(strict=True)):
            raise PolicyDenied("UNAUTHORIZED_VERIFICATION_PATH")
        if path.is_file() and path.stat().st_size <= 1024 * 1024:
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            result = "passed" if actual_hash == expected.value else "failed"
            evidence = "file_sha256=" + actual_hash
    except OSError:
        pass
    return Verification(task_id=task.id, generation=task.generation, goal_id=expected.goal_id,
                        method="file_content", result=result, evidence=evidence)
