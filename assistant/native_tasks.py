"""Restricted deterministic tasks used by the existing Controller, not a second service."""
from __future__ import annotations

import time

from .actions import LaunchApp, FocusWindow, FocusControl, TypeText
from .contracts import Goal, TaskStatus as S, TERMINAL
from .gateway import ToolGateway
from .notepad_backend import NotepadDraftBackend
from .policy import Policy, Scope, PolicyDenied
from .privacy import redact
from .service import InvalidTransition
from .system_backend import RegisteredSystemBackend, notepad_windows
from .verifier import Expected, verify_text, verify_window
from .windows_observer import DesktopLease, ContextWatchdog, observe_window


class NativeTasks:
    """Session-only ownership of a newly launched Notepad; no historical coordinate replay."""
    def __init__(self, service, stop, hotkey):
        self.service, self.stop, self.hotkey = service, stop, hotkey
        self.owned_draft = None
        self.gateway = None

    def run(self, command: str, *, source="text", original_text=None) -> None:
        """Execute only explicit launch / single-line input intents after local scope consent."""
        import comtypes
        from comtypes import COMError
        import win32gui
        is_launch = command.strip() == "打开记事本"
        text = command.removeprefix("输入：") if command.startswith("输入：") else None
        sensitive = redact(command) != command or any(word in command.lower() for word in ("密码", "验证码", "密钥", "password", "api_key"))
        task = self.service.create("敏感内容已省略" if sensitive else command, source=source,
            original_text="敏感内容已省略" if sensitive else original_text, goals=(Goal(predicate="window" if is_launch else "uia"),))
        comtypes.CoInitialize()
        lease, watcher = None, None
        try:
            lease = DesktopLease()
            self.service.transition(S.INTERPRETING)
            self.service.persist(self.service.task, "task.route", "deterministic")
            if sensitive:
                raise PolicyDenied("SENSITIVE_TEXT_NOT_SUPPORTED")
            if not is_launch and text is None:
                raise PolicyDenied("SUPPORTED_COMMANDS_OPEN_NOTEPAD_OR_INPUT")
            if not self.hotkey or not self.hotkey.registered or not lease.acquire():
                raise PolicyDenied("NATIVE_CONTROL_NOT_ARMED")
            self.service.transition(S.EXECUTING)
            policy = Policy(Scope(enabled=True, apps=frozenset({"notepad.exe"})))
            if is_launch:
                before = notepad_windows()
                backend = RegisteredSystemBackend(lease, self.hotkey, self.stop.event)
                self.gateway = ToolGateway(self.service, policy, object(), backend)
                self.gateway.observe(observe_window(win32gui.GetForegroundWindow()))
                action = LaunchApp(task_id=task.id, generation=task.generation, app_id="notepad.exe")
                self._dispatch(action)
                after = []
                until = time.monotonic() + 8
                while time.monotonic() < until and not self.stop.event.is_set():
                    after = notepad_windows()
                    if after:
                        break
                    self.stop.event.wait(.1)
                if not before and len(after) == 1:
                    self.owned_draft = after[0]
                if self.stop.event.is_set():
                    self.service.cancel()
                else:
                    self.service.finish([verify_window(self.service.task, Expected("primary","window","notepad.exe"), after[0] if after else None)])
                return
            if self.owned_draft is None:
                raise PolicyDenied("OPEN_A_NEW_NOTEPAD_FIRST")
            backend = NotepadDraftBackend(lease, self.hotkey, self.stop.event, self.owned_draft, text)
            self.gateway = ToolGateway(self.service, policy, object(), backend)
            target = self.owned_draft
            self.gateway.observe(observe_window(target.hwnd))
            self._dispatch(FocusWindow(task_id=task.id, generation=task.generation, hwnd=target.hwnd))
            self.service.observation = backend.observe_draft(require_focus=False)
            self._dispatch(FocusControl(task_id=task.id, generation=task.generation, control_id=self.service.observation.control_id))
            until = time.monotonic() + 1
            while True:
                try:
                    backend.observe_draft()
                    break
                except PolicyDenied:
                    if time.monotonic() >= until or self.stop.event.wait(.05):
                        raise
            watcher = ContextWatchdog(observe_window(target.hwnd), self.stop)
            watcher.start()
            for character in text:
                self.service.check_timeouts()
                if self.service.task.status in TERMINAL:
                    return
                self.service.observation = backend.observe_draft()
                self._dispatch(TypeText(task_id=task.id, generation=task.generation,
                    control_id=self.service.observation.control_id, text=character))
            self.service.finish([verify_text(self.service.task, Expected("primary","uia",text), backend.read_text())])
        except (PolicyDenied, InvalidTransition, OSError, RuntimeError, COMError) as exc:
            if self.service.task.status in TERMINAL or self.service.task.status == S.PAUSED:
                return
            code = str(exc) if isinstance(exc,PolicyDenied) else "NATIVE_TASK_ERROR"
            self.service.persist(self.service.task, "native.error", code)
            if self.stop.event.is_set():
                self.service.cancel()
            elif self.service.task.status == S.EXECUTING and self.service.task.action_count:
                self.service.finish([])
            else:
                self.service.transition(S.FAILED, error_code=code)
        finally:
            if watcher:
                watcher.close()
            if lease:
                lease.close()
            comtypes.CoUninitialize()

    def _dispatch(self, action) -> None:
        if self.service.pause_requested.is_set():
            self.service.pause_requested.clear()
            self.service.pause()
            self.service.pause_acknowledged()
            raise InvalidTransition("PAUSED_BEFORE_DISPATCH")
        result = self.gateway.dispatch(self.gateway.propose(action).id, action)
        if result.status != "ok":
            raise PolicyDenied(result.error_code or "TOOL_RESULT_UNKNOWN")
