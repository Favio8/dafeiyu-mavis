"""Read-only low-level Windows input monitoring. Never swallow user input."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading

from .notepad_backend import INPUT_TAG


class _KeyboardHook(ctypes.Structure):
    _fields_ = [("vk", wintypes.DWORD), ("scan", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]


class _MouseHook(ctypes.Structure):
    _fields_ = [("point", wintypes.POINT), ("data", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]


class InputMonitor:
    def __init__(self, stop: threading.Event):
        self.stop = stop
        self.changed = threading.Event()
        self.ready = threading.Event()
        self.error = None
        self.reason: str | None = None
        self.thread_id = 0
        self.thread = threading.Thread(target=self._run, name="mavis-native-input-monitor", daemon=True)

    def start(self):
        self.thread.start()
        if not self.ready.wait(2) or self.error:
            self.close()
            raise RuntimeError("INPUT_MONITOR_UNAVAILABLE")

    def _run(self):
        user = ctypes.WinDLL("user32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user.SetWindowsHookExW.argtypes = [ctypes.c_int, callback_type, wintypes.HINSTANCE, wintypes.DWORD]
        user.SetWindowsHookExW.restype = wintypes.HANDLE
        user.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user.CallNextHookEx.restype = ctypes.c_ssize_t
        user.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
        kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        self.thread_id = kernel.GetCurrentThreadId()

        def callback(structure, code, message, pointer):
            if code >= 0 and ctypes.cast(pointer, ctypes.POINTER(structure)).contents.extra != INPUT_TAG:
                self.reason = "USER_KEYBOARD_INPUT" if structure is _KeyboardHook else "USER_MOUSE_INPUT"
                self.changed.set()
                self.stop.set()
            return user.CallNextHookEx(None, code, message, pointer)

        self._key_callback = callback_type(lambda n, w, p: callback(_KeyboardHook, n, w, p))
        self._mouse_callback = callback_type(lambda n, w, p: callback(_MouseHook, n, w, p))
        module = kernel.GetModuleHandleW(None)
        key = user.SetWindowsHookExW(13, self._key_callback, module, 0)
        mouse = user.SetWindowsHookExW(14, self._mouse_callback, module, 0)
        try:
            if not key or not mouse:
                self.error = "INPUT_MONITOR_UNAVAILABLE"
                return
            self.ready.set()
            message = wintypes.MSG()
            while user.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                pass
        finally:
            self.ready.set()
            for handle in (key, mouse):
                if handle:
                    user.UnhookWindowsHookEx(handle)

    def close(self):
        if self.thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x12, 0, 0)
        if self.thread.is_alive():
            self.thread.join(timeout=.5)
