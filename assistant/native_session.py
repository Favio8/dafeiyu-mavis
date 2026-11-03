"""Host proxy: one permit dispatch becomes one bounded native-worker request."""
from __future__ import annotations

import ctypes
import json
import threading
import time
import os

from .actions import LaunchApp, FocusWindow, FocusControl, TypeText
from .contracts import Observation
from .ipc import WorkerSupervisor, ProtocolError
from .policy import PolicyDenied
from .system_backend import RegisteredSystemBackend


class NativeSession(RegisteredSystemBackend, WorkerSupervisor):
    MODULE = "assistant.native_worker"
    HOST_KINDS = {"hello", "stop", "native_request"}
    WORKER_KINDS = {"ready", "native_event"}

    def __init__(self, stop_controller, hotkey):
        WorkerSupervisor.__init__(self, stop_controller.event, on_message=self._message, on_failure=stop_controller.trip)
        self.stop_controller, self.hotkey = stop_controller, hotkey
        self.condition = threading.Condition()
        self.responses = {}
        self.request_seq = 0
        self.expected = None
        self.target = None
        self.pending_character = None
        self.shared_stop = None
        self.dispatches = []
        self.revocation_code: str | None = None

    def bootstrap(self):
        from .native_event import NativeStopEvent
        name = "Local\\DaFeiYuMavis.NativeStop."+self.session
        self.shared_stop = NativeStopEvent(name, create=True)
        return json.dumps({"stop_event":name,"parent_pid":os.getpid()})

    def signal_stop(self):
        self.intentional = True
        if self.shared_stop:
            self.shared_stop.set()

    def open(self, task, *, target=None, text=None):
        if not self.hotkey or not self.hotkey.registered:
            raise PolicyDenied("NATIVE_CONTROL_NOT_ARMED")
        self.stop_controller.own(self)
        WorkerSupervisor.start(self, task.id, task.generation)
        until = time.monotonic()+5
        while not self.ready.wait(.025):
            if self.stop.is_set() or self.ended.is_set() or time.monotonic() >= until:
                self.terminate()
                raise PolicyDenied("NATIVE_WORKER_NOT_READY")
        self.target = target
        self._call("setup", target=target.model_dump(mode="json") if target else None, text=text, **self.setup_extra())

    def setup_extra(self):
        return {}

    def _message(self, message):
        if message.kind != "native_event":
            return
        value = json.loads(message.payload)
        if value.get("event") == "revoked":
            self.revocation_code = value["code"]
            self.stop_controller.trip()
        elif value.get("event") == "dispatch":
            self.dispatches.append(value)
        else:
            with self.condition:
                self.responses[value["request"]] = value
                self.condition.notify_all()

    def _call(self, operation, **fields):
        if self.stop.is_set():
            raise PolicyDenied("STOPPED")
        self.request_seq += 1
        request = self.request_seq
        try:
            self.send("native_request", json.dumps({"request": request, "operation": operation, **fields}, ensure_ascii=False))
            deadline = time.monotonic()+5
            with self.condition:
                while request not in self.responses:
                    if self.stop.is_set():
                        raise PolicyDenied("STOPPED")
                    if self.ended.is_set() or time.monotonic() >= deadline:
                        self.stop_controller.trip()
                        raise RuntimeError("NATIVE_RESULT_UNKNOWN")
                    self.condition.wait(.025)
                result = self.responses.pop(request)
            if self.stop.is_set():
                raise PolicyDenied("STOPPED")
            if not result["ok"]:
                if result["code"] == "NATIVE_RESULT_UNKNOWN":
                    raise RuntimeError("NATIVE_RESULT_UNKNOWN")
                raise PolicyDenied(result["code"])
            return result["data"]
        except (OSError, ProtocolError):
            self.stop_controller.trip()
            raise RuntimeError("NATIVE_RESULT_UNKNOWN") from None

    def permits(self, action):
        return (isinstance(action, (FocusWindow, FocusControl)) or isinstance(action, TypeText) and len(action.text) == 1) if self.target else isinstance(action, LaunchApp) and action.app_id == "notepad.exe"

    def execute(self, action, stop):
        if stop is not self.stop or stop.is_set() or not self.hotkey.registered or not self.permits(action):
            raise PolicyDenied("NATIVE_CONTROL_NOT_ARMED")
        self.pending_character = action.text if isinstance(action, TypeText) else None
        try:
            result = self._call("execute", action=action.model_dump(mode="json"), observation=self.expected.model_dump(mode="json"))
        except PolicyDenied as exc:
            if str(exc) != "STOPPED":
                self.pending_character = None
            raise
        self.pending_character = None
        return result

    def observe_draft(self, *, require_focus=True):
        return Observation.model_validate_json(json.dumps(self._call("observe", require_focus=require_focus)))

    def seal(self, target):
        return Observation.model_validate_json(json.dumps(self._call("seal", target=target.model_dump(mode="json"))))

    def read_text(self):
        return self._call("read_text")

    def watch(self):
        self._call("watch")

    def terminate(self):
        self.signal_stop()
        WorkerSupervisor.terminate(self)
        # Only release our pending Unicode key; never synthesize text or release
        # user-held modifiers. The worker is already dead before this cleanup.
        character, self.pending_character = self.pending_character, None
        if character:
            from .notepad_backend import _Input, _Keyboard, INPUT_TAG
            packet = _Input()
            packet.kind = 1
            packet.payload.keyboard = _Keyboard(0, ord(character), 0x0006, 0, INPUT_TAG)
            user = ctypes.WinDLL("user32", use_last_error=True)
            user.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(_Input), ctypes.c_int]
            user.SendInput(1, ctypes.byref(packet), ctypes.sizeof(_Input))

    def close(self):
        WorkerSupervisor.close(self)
        if self.shared_stop:
            self.shared_stop.close()
