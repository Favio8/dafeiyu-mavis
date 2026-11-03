"""Diagnostic-only backend for a nonce-bound child window, never a product scope."""
from pathlib import Path
import sys

from .notepad_backend import NotepadDraftBackend
from .policy import PolicyDenied


class FixtureDraftBackend(NotepadDraftBackend):
    ALLOWED_APP = Path(sys.executable).name.lower()
    MAX_TEXT = 4096

    def __init__(self, lease, hotkey, stop, target, text, *, title, prefix, host_pid):
        import psutil
        import win32gui
        process = psutil.Process(target.pid)
        if host_pid not in {p.pid for p in process.parents()}:
            raise PolicyDenied("FIXTURE_PARENT_MISMATCH")
        expected_executable = sys.executable if getattr(sys,"frozen",False) else sys._base_executable
        if Path(process.exe()).resolve() != Path(expected_executable).resolve():
            raise PolicyDenied("FIXTURE_EXECUTABLE_MISMATCH")
        if win32gui.GetWindowText(target.hwnd) != title:
            raise PolicyDenied("FIXTURE_TITLE_MISMATCH")
        if not title.startswith("Mavis safety fixture ") or any(c != "m" for c in prefix+text):
            raise PolicyDenied("INVALID_FIXTURE_GOAL")
        self.field_name = title+" field"
        super().__init__(lease,hotkey,stop,target,text,sealing=True)
        self.prefix = prefix

    def _is_editor(self, element):
        return element.CurrentControlType == 50004 and (element.CurrentName == self.field_name or element.CurrentClassName == "Edit" and element.CurrentAutomationId == "15")
