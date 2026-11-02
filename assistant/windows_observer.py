"""Read-only Windows identity observations and a session-wide executor lease."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import threading
import time

from .contracts import Observation
from .policy import PolicyDenied, digest


def input_desktop_is_default() -> bool:
    """Return false for locked/secure/unreadable desktops; never switch desktops."""
    if os.name != "nt":
        return False
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    user.OpenInputDesktop.restype = wintypes.HANDLE
    user.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    user.CloseDesktop.argtypes = [wintypes.HANDLE]
    desktop = user.OpenInputDesktop(0, False, 1)
    if not desktop:
        return False
    try:
        name, needed = ctypes.create_unicode_buffer(128), wintypes.DWORD()
        ok = user.GetUserObjectInformationW(desktop, 2, name, ctypes.sizeof(name), ctypes.byref(needed))
        return bool(ok and name.value == "Default")
    finally:
        user.CloseDesktop(desktop)


def observe_window(hwnd: int) -> Observation:
    """Bind a specific HWND to PID, process birth/executable, bounds, DPI and integrity.

    This does not read window titles, UI text or screenshots. It grants no control
    semantics: safe_control/editable_draft remain false until a trusted UIA adapter
    establishes them. Errors use fixed codes rather than leaking OS path strings.
    """
    import psutil
    import win32api
    import win32con
    import win32gui
    import win32process
    import win32security
    if not input_desktop_is_default() or not win32gui.IsWindow(hwnd):
        raise PolicyDenied("DESKTOP_OR_WINDOW_UNAVAILABLE")
    try:
        _thread, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        executable, born = process.exe(), process.create_time()
        handle = win32api.OpenProcess(0x1000, False, pid)
        try:
            token = win32security.OpenProcessToken(handle, win32con.TOKEN_QUERY)
            try:
                sid, _attributes = win32security.GetTokenInformation(token, win32security.TokenIntegrityLevel)
                rid = sid.GetSubAuthority(sid.GetSubAuthorityCount() - 1)
            finally:
                token.Close()
        finally:
            handle.Close()
        integrity = "medium" if 0x2000 <= rid < 0x3000 else "high" if rid >= 0x3000 else "unknown"
        bounds = tuple(win32gui.GetWindowRect(hwnd))
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.GetDpiForWindow.argtypes = [wintypes.HWND]
        user.GetDpiForWindow.restype = wintypes.UINT
        dpi = user.GetDpiForWindow(hwnd)
        foreground = win32gui.GetForegroundWindow()
        if dpi == 0:
            raise PolicyDenied("WINDOW_DPI_UNAVAILABLE")
        context = {"hwnd": hwnd, "pid": pid, "birth": born, "exe": executable.casefold(),
                   "bounds": bounds, "dpi": dpi, "foreground": foreground, "integrity": integrity}
        return Observation(captured_mono=time.monotonic(), context_digest=digest(context), hwnd=hwnd, pid=pid,
                           app=Path(executable).name.lower(), integrity=integrity, own_ui=pid == os.getpid(), bounds=bounds, dpi=dpi)
    except (psutil.Error, OSError, win32api.error):
        raise PolicyDenied("WINDOW_IDENTITY_UNAVAILABLE") from None


class DesktopLease:
    """One desktop executor per Windows user/session, across all data directories.

    Acquire/release must occur on the owner thread. No filesystem lock or PID file
    is trusted, and no abandoned lease resumes the previous task.
    """
    _guard = threading.Lock()
    _owned: set[str] = set()

    def __init__(self):
        import win32api
        import win32con
        import win32security
        token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
        try:
            sid = win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token, win32security.TokenUser)[0])
        finally:
            token.Close()
        self.name = "Local\\DaFeiYuMavis.DesktopControl." + sid
        self.handle = None
        self.owner = None
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]

    def acquire(self) -> bool:
        """Try once; refuse same-thread recursive ownership as well as other processes."""
        with self._guard:
            if self.handle or self.name in self._owned:
                return False
            handle = self.kernel.CreateMutexW(None, False, self.name)
            if not handle:
                raise PolicyDenied("LEASE_UNAVAILABLE")
            result = self.kernel.WaitForSingleObject(handle, 0)
            if result not in (0, 0x80):
                self.kernel.CloseHandle(handle)
                if result != 0x102:
                    raise PolicyDenied("LEASE_UNAVAILABLE")
                return False
            self.handle, self.owner = handle, threading.get_ident()
            self._owned.add(self.name)
            return True

    def close(self) -> None:
        """Release only this owned mutex, on the acquiring thread."""
        with self._guard:
            if self.handle:
                if threading.get_ident() != self.owner:
                    raise RuntimeError("lease must be released by its owner thread")
                if not self.kernel.ReleaseMutex(self.handle):
                    raise PolicyDenied("LEASE_RELEASE_FAILED")
                self.kernel.CloseHandle(self.handle)
                self.handle = None
                self._owned.discard(self.name)


class ContextWatchdog:
    """Independent monitoring prototype. Does not replace native session/input hooks."""
    def __init__(self, expected: Observation, stop, observer=observe_window):
        self.expected, self.stop, self.observer = expected, stop, observer
        self.closed = threading.Event()
        self.reason: str | None = None
        self.thread = threading.Thread(target=self._run, name="mavis-context-watchdog", daemon=True)

    def start(self) -> None:
        """Start monitoring one bound context; no keyboard/mouse events are generated."""
        self.thread.start()

    def _run(self) -> None:
        previous = time.monotonic()
        while not self.closed.wait(.05):
            now = time.monotonic()
            try:
                if now - previous > 2:
                    raise PolicyDenied("SESSION_TIME_GAP")
                current = self.observer(self.expected.hwnd)
                if current.context_digest != self.expected.context_digest:
                    raise PolicyDenied("CONTEXT_CHANGED")
            except (PolicyDenied, OSError):
                self.reason = "CONTEXT_OR_SESSION_LOST"
                self.stop.trip()
                return
            previous = now

    def close(self) -> None:
        """Stop the monitor without resetting an already tripped stop latch."""
        self.closed.set()
        self.thread.join(timeout=1)
