"""Fail-closed local policy, independent of prompts, pages and model risk labels."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .actions import Click, CreateFile, FixtureAction, FocusWindow, FocusControl, LaunchApp, OpenURL, Scroll, Shortcut, TypeText
from .contracts import Observation
from .privacy import redact


class PolicyDenied(ValueError):
    """A stable reason code for a refused action; raw tool content is not logged."""


@dataclass(frozen=True)
class Scope:
    """Host settings, never parsed from worker messages or observation text."""
    enabled: bool = False
    apps: frozenset[str] = frozenset()
    domains: frozenset[str] = frozenset()
    folders: tuple[Path, ...] = ()
    version: int = 1


def digest(value) -> str:
    """Hash canonical structured parameters, including all action identity fields."""
    data = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def normalize_url(raw: str) -> str:
    """Accept only explicit HTTPS URLs without credentials, ambiguous escapes or ports."""
    if redact(raw) != raw:
        raise PolicyDenied("SENSITIVE_URL")
    if any(ord(c) < 33 for c in raw) or "\\" in raw or re.search(r"%(?:0[0-9a-f]|1[0-9a-f]|7f)", raw, re.I):
        raise PolicyDenied("INVALID_URL")
    try:
        parts = urlsplit(raw)
        if parts.scheme.lower() != "https" or not parts.hostname or parts.username or parts.password:
            raise PolicyDenied("FORBIDDEN_URL")
        if parts.port not in (None, 443) or parts.fragment or "%" in parts.netloc:
            raise PolicyDenied("AMBIGUOUS_URL")
        host = parts.hostname.encode("idna").decode("ascii").lower()
        if host.endswith(".") or not re.fullmatch(r"[a-z0-9.-]+", host):
            raise PolicyDenied("INVALID_HOST")
    except (ValueError, UnicodeError) as exc:
        raise PolicyDenied("INVALID_URL") from exc
    return urlunsplit(("https", host, parts.path or "/", parts.query, ""))


def new_file_path(raw: str, roots: tuple[Path, ...]) -> Path:
    """Validate an absent file inside existing non-reparse directories.

    M2 must repeat this immediately before exclusive creation; this check alone
    cannot protect against a same-user process replacing directories concurrently.
    """
    if "\x00" in raw or raw.startswith(("\\\\", "//")) or any(c in raw for c in "*?<>|\""):
        raise PolicyDenied("INVALID_PATH")
    path = Path(raw)
    if not path.is_absolute() or ".." in path.parts:
        raise PolicyDenied("PATH_TRAVERSAL")
    for part in path.parts[1:]:
        if part.endswith((".", " ")) or ":" in part or re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", part, re.I):
            raise PolicyDenied("AMBIGUOUS_PATH")
    for parent in (path, *path.parents):
        if parent.exists() or parent.is_symlink():
            info = parent.lstat()
            if parent.is_symlink() or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise PolicyDenied("REPARSE_PATH")
    resolved = path.resolve()
    if not path.parent.is_dir() or path.exists():
        raise PolicyDenied("EXISTING_OR_MISSING_PARENT")
    if not any(resolved.is_relative_to(root.resolve(strict=True)) for root in roots):
        raise PolicyDenied("OUTSIDE_AUTHORIZED_FOLDER")
    return resolved


_FORBIDDEN_APPS = {"cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe", "wt.exe",
                   "conhost.exe", "regedit.exe", "taskmgr.exe", "run", "consent.exe"}


class Policy:
    """Only the host constructs or replaces a scope. Unknown semantics remain RU."""
    def __init__(self, scope: Scope = Scope()):
        self.scope = scope

    def evaluate(self, action, observation: Observation, *, mode: str, now: float, max_age_ms: int):
        """Return (normalized action, local risk) or raise PolicyDenied before any effect."""
        if now < observation.captured_mono or (now - observation.captured_mono) * 1000 > max_age_ms:
            raise PolicyDenied("STALE_OBSERVATION")
        if isinstance(action, FixtureAction):
            if mode != "test" or observation.app != "mavis.fixture":
                raise PolicyDenied("TEST_ONLY")
            return action, "R1"
        if not self.scope.enabled:
            raise PolicyDenied("COMPUTER_CONTROL_DISABLED")
        # A registered application launch does not target the foreground window's
        # controls. It may originate in our own UI; GUI self-operation remains forbidden.
        if isinstance(action, LaunchApp):
            if observation.integrity != "medium" or not observation.hwnd or not observation.pid:
                raise PolicyDenied("UNTRUSTED_WINDOW")
            if action.app_id not in self.scope.apps or action.app_id.lower() in _FORBIDDEN_APPS:
                raise PolicyDenied("APP_NOT_ALLOWED")
            return action, "R0"
        if observation.own_ui or observation.pid == os.getpid():
            raise PolicyDenied("SELF_OPERATION")
        if observation.integrity != "medium" or observation.hwnd == 0 or observation.pid == 0:
            raise PolicyDenied("UNTRUSTED_WINDOW")
        app = observation.app.lower()
        if app in _FORBIDDEN_APPS or app not in self.scope.apps:
            raise PolicyDenied("APP_NOT_ALLOWED")
        if isinstance(action, FocusWindow):
            if action.hwnd != observation.hwnd:
                raise PolicyDenied("WINDOW_BINDING_MISMATCH")
            return action, "R0"
        if isinstance(action, FocusControl):
            if not observation.editable_draft or action.control_id != observation.control_id:
                raise PolicyDenied("NOT_TASK_DRAFT")
            return action, "R0"
        if isinstance(action, OpenURL):
            url = normalize_url(action.url)
            if urlsplit(url).hostname not in self.scope.domains:
                raise PolicyDenied("DOMAIN_NOT_ALLOWED")
            return action.model_copy(update={"url": url}), "R0"
        if isinstance(action, CreateFile):
            if redact(action.content) != action.content:
                raise PolicyDenied("SENSITIVE_CONTENT")
            path = new_file_path(action.path, self.scope.folders)
            return action.model_copy(update={"path": str(path)}), "R1"
        if observation.domain is not None and observation.domain not in self.scope.domains:
            raise PolicyDenied("DOMAIN_NOT_ALLOWED")
        if isinstance(action, TypeText):
            if redact(action.text) != action.text:
                raise PolicyDenied("SENSITIVE_CONTENT")
            if not observation.editable_draft or action.control_id != observation.control_id:
                raise PolicyDenied("NOT_TASK_DRAFT")
            # No line breaks, tabs or key syntax can become implicit submissions.
            if any(ord(c) < 32 for c in action.text):
                raise PolicyDenied("CONTROL_CHARACTER")
            return action, "R0"
        if isinstance(action, Click):
            if not observation.safe_control or action.control_id != observation.control_id:
                raise PolicyDenied("UNKNOWN_CONTROL_SEMANTICS")
            return action, "R0"
        if isinstance(action, Scroll):
            if not observation.safe_control:
                raise PolicyDenied("UNKNOWN_CONTROL_SEMANTICS")
            return action, "R0"
        if isinstance(action, Shortcut):
            if not observation.editable_draft or action.keys.lower() not in {"ctrl+a", "ctrl+f", "escape"}:
                raise PolicyDenied("FORBIDDEN_SHORTCUT")
            return action.model_copy(update={"keys": action.keys.lower()}), "R0"
        raise PolicyDenied("UNKNOWN_ACTION")
