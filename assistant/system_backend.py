"""Narrow L1 executor: registered Notepad launch only. No shell, URI or GUI input."""
from __future__ import annotations

from pathlib import Path
import threading

from .actions import LaunchApp
from .contracts import Observation
from .policy import PolicyDenied
from .windows_observer import DesktopLease, observe_window, input_desktop_is_default


class RegisteredSystemBackend:
    """Explicit host-owned lease and real hotkey registration are mandatory.

    Keeping this registry fixed makes a model-supplied executable path impossible.
    This does not enable URL handlers, folder opening, or keyboard/mouse input.
    """
    def __init__(self, lease: DesktopLease, hotkey, stop: threading.Event):
        import win32api
        self.registry = {"notepad.exe": Path(win32api.GetSystemDirectory()) / "notepad.exe"}
        self.lease, self.hotkey, self.stop = lease, hotkey, stop
        self.expected: Observation | None = None
        self.launched_pid: int | None = None

    def permits(self, action) -> bool:
        """Reject every unimplemented action, independent of schema or model confidence."""
        return isinstance(action, LaunchApp) and action.app_id == "notepad.exe"

    def bind(self, observed: Observation) -> None:
        """Bind the trusted host observation used by the gateway; no model-supplied context."""
        self.expected = observed

    def execute(self, action, stop: threading.Event) -> str:
        """Recheck stop, OS identity and desktop immediately before one fixed process launch."""
        if not self.permits(action):
            raise PolicyDenied("SYSTEM_TOOL_NOT_IMPLEMENTED")
        if stop is not self.stop or stop.is_set():
            raise PolicyDenied("STOPPED")
        if not self.lease.handle or self.lease.owner != threading.get_ident() or not self.hotkey.registered:
            raise PolicyDenied("NATIVE_CONTROL_NOT_ARMED")
        if self.expected is None or not input_desktop_is_default():
            raise PolicyDenied("NO_NATIVE_CONTEXT")
        current = observe_window(self.expected.hwnd)
        if current.context_digest != self.expected.context_digest or current.integrity != "medium":
            raise PolicyDenied("CONTEXT_CHANGED")
        path = self.registry[action.app_id]
        if not path.is_file() or path.is_symlink():
            raise PolicyDenied("REGISTERED_APPLICATION_UNAVAILABLE")
        if stop.is_set():
            raise PolicyDenied("STOPPED")
        import win32api
        import win32con
        import win32process
        from win32com.shell import shell, shellcon
        try:
            if stop.is_set() or observe_window(self.expected.hwnd).context_digest != self.expected.context_digest:
                raise PolicyDenied("STOPPED_OR_CONTEXT_CHANGED")
            from .frozen_environment import external_application
            with external_application():
                result = shell.ShellExecuteEx(fMask=shellcon.SEE_MASK_NOCLOSEPROCESS | shellcon.SEE_MASK_FLAG_NO_UI,
                    lpVerb="open", lpFile=str(path), nShow=win32con.SW_SHOWNORMAL)
            handle = result.get("hProcess")
            if handle:
                try:
                    self.launched_pid = win32process.GetProcessId(handle)
                finally:
                    win32api.CloseHandle(handle)
        except win32api.error:
            raise PolicyDenied("REGISTERED_LAUNCH_FAILED") from None
        return "已向 Windows 发起启动记事本；目标窗口尚需独立验证"


def notepad_windows() -> list[Observation]:
    """Observe only visible Notepad windows; do not read titles or document contents."""
    import psutil
    import win32gui
    import win32process
    found = []
    def visit(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            pid = win32process.GetWindowThreadProcessId(hwnd)[1]
            if psutil.Process(pid).name().casefold() == "notepad.exe":
                found.append(observe_window(hwnd))
        except (psutil.Error, PolicyDenied, OSError):
            return
    win32gui.EnumWindows(visit, None)
    return found
