"""Restricted GUI pilot: a newly launched empty Notepad, one Unicode scalar per grant.

UIA COM activation follows the audited Windows-Use UIA core seam, but imports no
Windows-Use Agent/providers. This is not a general Windows-Use adapter or UIA tree.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading
import time

from .actions import FocusWindow, FocusControl, TypeText
from .contracts import Observation
from .policy import PolicyDenied, digest
from .system_backend import RegisteredSystemBackend
from .windows_observer import observe_window

INPUT_TAG = 0x4D41564953


class _Keyboard(ctypes.Structure):
    _fields_ = [("vk", wintypes.WORD), ("scan", wintypes.WORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]


class _Mouse(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG), ("data", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]


class _Payload(ctypes.Union):
    _fields_ = [("keyboard", _Keyboard), ("mouse", _Mouse)]


class _Input(ctypes.Structure):
    _fields_ = [("kind", wintypes.DWORD), ("payload", _Payload)]


class NotepadDraftBackend(RegisteredSystemBackend):
    """Host constructs this only for a newly observed window with an empty document.

    No file save, clipboard, shortcut, arbitrary click, drag or shell path exists.
    The expected text comes from the host-confirmed goal, not page/model content.
    """
    ALLOWED_APP = "notepad.exe"
    MAX_TEXT = 16

    def __init__(self, lease, hotkey, stop, target: Observation, text: str, *, sealing=False):
        super().__init__(lease, hotkey, stop)
        if target.app != self.ALLOWED_APP or target.integrity != "medium" or target.own_ui:
            raise PolicyDenied("NOT_A_SAFE_NOTEPAD")
        if not text or len(text) > self.MAX_TEXT or any(ord(c) < 32 or ord(c) > 0xFFFF for c in text):
            raise PolicyDenied("PILOT_TEXT_OUT_OF_RANGE")
        if not sealing and (not target.control_id or not target.document_digest):
            raise PolicyDenied("DRAFT_NOT_SEALED")
        import comtypes.client
        self.types = comtypes.client.GetModule("UIAutomationCore.dll")
        self.uia = comtypes.client.CreateObject("{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=self.types.IUIAutomation)
        self.target, self.goal_text, self.prefix = target, text, ""
        self.editor_id = target.control_id or None
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.user.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int]
        self.user.SendInput.restype = wintypes.UINT
        self.user.GetAsyncKeyState.argtypes = [ctypes.c_int]

    def permits(self, action) -> bool:
        """Expose only window focus and single-character text within the confirmed goal."""
        return isinstance(action, (FocusWindow, FocusControl, TypeText))

    def _editor(self):
        root = self.uia.ElementFromHandle(self.target.hwnd)
        condition = self.uia.CreateOrCondition(self.uia.CreatePropertyCondition(30003,50030), self.uia.CreatePropertyCondition(30003,50004))
        elements = root.FindAll(4, condition)
        candidates = []
        for index in range(elements.Length):
            element = elements.GetElement(index)
            if element.CurrentIsOffscreen or element.CurrentIsPassword or not element.CurrentIsEnabled:
                continue
            if self._is_editor(element):
                candidates.append(element)
        if len(candidates) != 1 or candidates[0].CurrentProcessId != self.target.pid:
            raise PolicyDenied("EDITOR_NOT_UNIQUE")
        return candidates[0]

    def _is_editor(self, element):
        return element.CurrentControlType == 50030 or (element.CurrentControlType == 50004 and element.CurrentClassName == "Edit" and element.CurrentAutomationId == "15")

    def _focused_editor(self):
        import win32gui
        if win32gui.GetForegroundWindow() != self.target.hwnd:
            raise PolicyDenied("FOCUS_CHANGED")
        element = self.uia.GetFocusedElement()
        if element.CurrentProcessId != self.target.pid or not self._is_editor(element):
            raise PolicyDenied("NOT_FOCUSED_EDITOR")
        if element.CurrentIsPassword or not element.CurrentIsEnabled or element.CurrentIsOffscreen:
            raise PolicyDenied("EDITOR_UNAVAILABLE")
        root = self.uia.ElementFromHandle(self.target.hwnd)
        parent = element
        for _ in range(16):
            if self.uia.CompareElements(root, parent):
                break
            parent = self.uia.ControlViewWalker.GetParentElement(parent)
            if not parent:
                raise PolicyDenied("EDITOR_OUTSIDE_WINDOW")
        else:
            raise PolicyDenied("EDITOR_OUTSIDE_WINDOW")
        return element

    def read_text(self) -> str:
        """Independent UIA document read, limited to this bound focused draft."""
        from comtypes import COMError
        import win32gui
        try:
            if self.stop.is_set():
                raise PolicyDenied("STOPPED")
            before = observe_window(self.target.hwnd)
            if not self.target.identity_digest or before.identity_digest != self.target.identity_digest or before.integrity!="medium" or before.own_ui:
                raise PolicyDenied("WINDOW_REPLACED")
            title = win32gui.GetWindowText(self.target.hwnd).removeprefix("*")
            title_digest = digest(title)
            if self.target.document_digest and title_digest != self.target.document_digest:
                raise PolicyDenied("DOCUMENT_REPLACED")
            element = self._editor()
            runtime_id = ":".join(str(x) for x in element.GetRuntimeId())
            if self.editor_id is not None and runtime_id != self.editor_id:
                raise PolicyDenied("EDITOR_REPLACED")
            try:
                pattern = element.GetCurrentPattern(10002).QueryInterface(self.types.IUIAutomationValuePattern)
                value = pattern.CurrentValue
            except COMError:
                pattern = element.GetCurrentPattern(10014).QueryInterface(self.types.IUIAutomationTextPattern)
                value = pattern.DocumentRange.GetText(4097)
            if len(value) > 4096:
                raise PolicyDenied("NOT_A_NEW_DRAFT")
            # Pilot accepts a single line; UIA's document paragraph terminator is not user text.
            after = observe_window(self.target.hwnd)
            after_title = digest(win32gui.GetWindowText(self.target.hwnd).removeprefix("*"))
            if self.stop.is_set():
                raise PolicyDenied("STOPPED")
            if after.context_digest != before.context_digest or after_title != title_digest:
                raise PolicyDenied("CONTEXT_CHANGED_DURING_READ")
            # Never erase user newlines to turn a mismatch into success. Providers
            # with implicit terminators require separate calibration, not guessing.
            return value
        except (COMError, AttributeError, TypeError):
            raise PolicyDenied("UIA_TEXT_UNAVAILABLE") from None

    def observe_draft(self, *, require_focus: bool = True) -> Observation:
        """Only a verified empty/expected-prefix draft acquires editable semantics."""
        root = observe_window(self.target.hwnd)
        if root.pid != self.target.pid or root.app != self.ALLOWED_APP or root.integrity != "medium" or not self.target.identity_digest or root.identity_digest != self.target.identity_digest:
            raise PolicyDenied("WINDOW_REPLACED")
        text = self.read_text()
        if text != self.prefix:
            raise PolicyDenied("DRAFT_CHANGED_BY_OTHER_INPUT")
        element = self._focused_editor() if require_focus else self._editor()
        runtime_id = ":".join(str(x) for x in element.GetRuntimeId())
        self.editor_id = runtime_id
        return root.model_copy(update={"control_id":runtime_id, "editable_draft":True,
            "document_digest":self.target.document_digest,
            "context_digest":digest({"window":root.context_digest,"editor":runtime_id,"text":text})})

    def execute(self, action, stop: threading.Event) -> str:
        """One finite OS action after grant consumption; a partial send stops the task."""
        import win32gui
        if stop is not self.stop or stop.is_set() or not self.hotkey.registered or not self.lease.handle or self.lease.owner != threading.get_ident():
            raise PolicyDenied("NATIVE_CONTROL_NOT_ARMED")
        if self.expected is None or self.expected.hwnd != self.target.hwnd or self.expected.pid != self.target.pid:
            raise PolicyDenied("WINDOW_BINDING_MISMATCH")
        if not 0 <= time.monotonic() - self.expected.captured_mono <= 2:
            raise PolicyDenied("STALE_NATIVE_OBSERVATION")
        if isinstance(action, FocusWindow):
            if action.hwnd != self.target.hwnd or observe_window(action.hwnd).context_digest != self.expected.context_digest:
                raise PolicyDenied("CONTEXT_CHANGED")
            if win32gui.GetForegroundWindow() == action.hwnd:
                return "受控目标已在前台，无需切换"
            try:
                if stop.is_set():
                    raise PolicyDenied("STOPPED")
                win32gui.SetForegroundWindow(action.hwnd)
            except win32gui.error:
                raise PolicyDenied("FOCUS_NOT_GRANTED_BY_WINDOWS") from None
            return "已请求将受控记事本置前；尚需重新观察"
        if isinstance(action, FocusControl):
            current = self.observe_draft(require_focus=False)
            if current.context_digest != self.expected.context_digest or action.control_id != current.control_id:
                raise PolicyDenied("CONTEXT_CHANGED")
            if stop.is_set() or win32gui.GetForegroundWindow() != self.target.hwnd:
                raise PolicyDenied("STOPPED_OR_FOCUS_CHANGED")
            self._editor().SetFocus()
            return "已请求将空白草稿编辑区聚焦；尚需独立检查"
        if not isinstance(action, TypeText) or len(action.text) != 1 or not self.goal_text.startswith(self.prefix + action.text):
            raise PolicyDenied("PILOT_GOAL_MISMATCH")
        current = self.observe_draft()
        if current.context_digest != self.expected.context_digest or current.control_id != action.control_id:
            raise PolicyDenied("CONTEXT_CHANGED")
        if any(self.user.GetAsyncKeyState(key) & 0x8000 for key in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
            raise PolicyDenied("USER_MODIFIER_HELD")
        if stop.is_set() or win32gui.GetForegroundWindow() != self.target.hwnd:
            raise PolicyDenied("STOPPED_OR_FOCUS_CHANGED")
        inputs = (_Input * 2)()
        for index, flags in enumerate((0x0004, 0x0006)):
            inputs[index].kind = 1
            inputs[index].payload.keyboard = _Keyboard(0, ord(action.text), flags, 0, INPUT_TAG)
        notice = getattr(self, "dispatch_notice", None)
        if notice:
            notice("begin", time.perf_counter(), 2)
        if stop.is_set():
            raise PolicyDenied("STOPPED")
        sent = self.user.SendInput(2, inputs, ctypes.sizeof(_Input))
        if notice:
            notice("returned", time.perf_counter(), sent)
        if sent != 2:
            if sent == 1:
                self.user.SendInput(1, ctypes.byref(inputs[1]), ctypes.sizeof(_Input))
            stop.set()
            raise RuntimeError("PARTIAL_UNICODE_INPUT")
        expected = self.prefix + action.text
        deadline = time.monotonic() + 1
        while not stop.is_set() and time.monotonic() < deadline:
            if self.read_text() == expected:
                self.prefix = expected
                return "已通过 Unicode 输入一个字符；UIA 后置读取匹配"
            stop.wait(.02)
        raise RuntimeError("INPUT_RESULT_UNKNOWN")
