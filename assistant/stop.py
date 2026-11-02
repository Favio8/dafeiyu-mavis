"""Independent stop latch and Windows message-thread hotkey; no Qt/LLM dependency."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import threading
import time
import re
import subprocess


def shortcut_key(shortcut: str) -> int:
    match = re.fullmatch(r"Ctrl\+Alt\+(F(?:[1-9]|1[0-2])|[A-Z]|Space)", shortcut)
    if not match:
        raise ValueError("快捷键格式为 Ctrl+Alt+F1～F12、字母或 Space")
    key = match[1]
    return 0x20 if key == "Space" else 0x6F+int(key[1:]) if key.startswith("F") and len(key)>1 else ord(key)


class StopController:
    """Revoke dispatch first, then terminate only owned workers."""
    def __init__(self):
        self.event = threading.Event()
        self._workers = []
        self._lock = threading.Lock()
        self.last_stop_ms: float | None = None
        self.tripped_mono: float | None = None
        self.termination_errors = []

    def own(self, worker) -> None:
        """Register a supervisor before its process starts; late registration fails closed."""
        with self._lock:
            self._workers = [w for w in self._workers if (w.process is None and not getattr(w, "intentional", False)) or w.process is not None and not w.actual_exited()]
            self._workers.append(worker)
            if self.event.is_set():
                worker.terminate()

    def trip(self) -> None:
        """Called directly from UI or hotkey thread; does not wait for controller/LLM work."""
        start = time.perf_counter()
        if self.tripped_mono is None:
            self.tripped_mono = time.monotonic()
        self.event.set()
        with self._lock:
            workers = tuple(self._workers)
        for worker in workers:
            signal = getattr(worker, "signal_stop", None)
            if callable(signal):
                signal()
        for worker in workers:
            try:
                worker.terminate()
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                self.termination_errors.append(type(exc).__name__)
        self.last_stop_ms = max(self.last_stop_ms or 0, (time.perf_counter() - start) * 1000)

    def reset(self) -> None:
        """Explicit reset for a new task only, after all owned processes have exited."""
        with self._lock:
            if any(w.process is not None and not w.actual_exited() for w in self._workers):
                raise RuntimeError("worker still alive")
            self.event.clear()
            self.tripped_mono = None
            self.last_stop_ms = None
            self.termination_errors.clear()


class EmergencyHotkey:
    """Register Ctrl+Alt+F12 on a dedicated Windows thread, with visible failure state."""
    HOTKEY_ID = 0x4D56
    VKEY = 0x7B

    def __init__(self, stop: StopController, shortcut=None):
        self.stop = stop
        self.vkey = shortcut_key(shortcut) if shortcut else self.VKEY
        self.shortcut = shortcut or ("Ctrl+Alt+Space" if self.VKEY == 0x20 else "Ctrl+Alt+F12")
        self.registered = False
        self.physical_seen = False
        self.error: str | None = None
        self.thread_id = 0
        self.received_mono = None
        self.received_perf = None
        self.ready = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> bool:
        """Wait briefly for the real OS registration result, never assume success."""
        if os.name != "nt":
            self.error = "WINDOWS_REQUIRED"
            return False
        self.thread = threading.Thread(target=self._run, name="mavis-emergency-hotkey", daemon=True)
        self.thread.start()
        if not self.ready.wait(2):
            self.error = "HOTKEY_REGISTRATION_TIMEOUT"
            return False
        return self.registered

    def _run(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.thread_id = kernel32.GetCurrentThreadId()
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self.registered = bool(user32.RegisterHotKey(None, self.HOTKEY_ID, 0x4003, self.vkey))
        if not self.registered:
            self.error = f"HOTKEY_UNAVAILABLE_{ctypes.get_last_error()}"
        self.ready.set()
        if not self.registered:
            return
        message = wintypes.MSG()
        try:
            while True:
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    if result < 0:
                        self.error = "HOTKEY_MESSAGE_ERROR"
                        self.stop.trip()
                    break
                if message.message == 0x0312 and message.wParam == self.HOTKEY_ID:
                    self.received_mono = time.monotonic()
                    self.received_perf = time.perf_counter()
                    self.physical_seen = True
                    self._trigger()
        finally:
            user32.UnregisterHotKey(None, self.HOTKEY_ID)
            self.registered = False

    def _trigger(self):
        self.stop.trip()

    def close(self) -> None:
        """Release only this thread's hotkey and end its message loop."""
        if self.thread_id and self.registered:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
        if self.thread:
            self.thread.join(timeout=2)
