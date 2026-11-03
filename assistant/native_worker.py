"""One fixed native backend per task; no model, shell or database authority."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
import queue
import sys
import threading
import time
from types import SimpleNamespace

from .ipc import MAX_MESSAGE, Message, Receiver, decode, encode, ProtocolError


def main():
    import comtypes
    from .actions import ACTION_SCHEMA
    from .contracts import Observation
    from .native_input_monitor import InputMonitor
    from .notepad_backend import NotepadDraftBackend
    from .system_backend import RegisteredSystemBackend
    from .policy import digest
    from .windows_observer import DesktopLease, ContextWatchdog, input_desktop_is_default, observe_window
    from .policy import PolicyDenied
    from .native_event import NativeStopEvent
    comtypes.CoInitialize()
    first = decode(sys.stdin.buffer.readline(MAX_MESSAGE+1))
    if first.kind != "hello" or first.role != "host" or first.seq != 1:
        return 2
    receiver = Receiver(first.session, "host", first.task_id, first.generation)
    receiver.accept(encode(first))
    sequence = 0
    writer = threading.Lock()
    commands = queue.Queue(maxsize=4)
    bootstrap = json.loads(first.payload)
    if bootstrap.get("stop_event") != "Local\\DaFeiYuMavis.NativeStop."+first.session:
        raise ProtocolError("invalid native stop binding")
    import psutil
    host_pid = bootstrap["parent_pid"]
    if host_pid not in {p.pid for p in psutil.Process().parents()}:
        raise ProtocolError("native host is not a process ancestor")
    stopped, ended = NativeStopEvent(bootstrap["stop_event"]), threading.Event()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    parent_handle = kernel.OpenProcess(0x100000, False, host_pid)
    if not parent_handle:
        return 2
    stopped.parent_handle=parent_handle
    lease, monitor, watcher, backend = DesktopLease(), InputMonitor(stopped), None, None

    def send(value):
        nonlocal sequence
        with writer:
            sequence += 1
            sys.stdout.buffer.write(encode(Message(session=first.session, role="worker", seq=sequence,
                task_id=first.task_id, generation=first.generation, kind="native_event", payload=json.dumps(value, ensure_ascii=False))))
            sys.stdout.buffer.flush()

    def read():
        try:
            while data := sys.stdin.buffer.readline(MAX_MESSAGE+1):
                commands.put(receiver.accept(data), timeout=1)
        except (OSError, ProtocolError, queue.Full):
            pass
        stopped.set()
        # A parent that vanished cannot leave a blocked COM call owning input.
        if not ended.is_set():
            os._exit(3)

    def safety_watch():
        previous = time.monotonic()
        while not ended.wait(.025):
            if kernel.WaitForSingleObject(parent_handle, 0) != 0x102:
                os._exit(3)
            now = time.monotonic()
            if monitor.changed.is_set() or (watcher and watcher.reason) or now-previous > 2 or not input_desktop_is_default():
                stopped.set()
                reason = monitor.reason or (watcher.reason if watcher else None) or ("SESSION_TIME_GAP" if now-previous > 2 else "INPUT_DESKTOP_UNAVAILABLE")
                send({"event": "revoked", "code": reason, "mono": now})
                return
            previous = now

    try:
        if not lease.acquire():
            raise PolicyDenied("DESKTOP_ALREADY_OWNED")
        monitor.start()
        sequence += 1
        sys.stdout.buffer.write(encode(Message(session=first.session, role="worker", seq=sequence, task_id=first.task_id,
            generation=first.generation, kind="ready", payload=str(os.getpid()))))
        sys.stdout.buffer.flush()
        threading.Thread(target=read, name="mavis-native-pipe", daemon=True).start()
        threading.Thread(target=safety_watch, name="mavis-native-safety", daemon=True).start()
        while not stopped.is_set():
            try:
                message = commands.get(timeout=.1)
            except queue.Empty:
                continue
            if message.kind == "stop":
                break
            if message.kind != "native_request":
                raise ProtocolError("unexpected native command")
            request = json.loads(message.payload)
            request_id = request["request"]
            try:
                operation = request["operation"]
                if operation == "setup":
                    target = request.get("target")
                    if request.get("fixture"):
                        if "--test-mode" not in sys.argv:
                            raise PolicyDenied("DIAGNOSTIC_MODE_REQUIRED")
                        from .native_fixture import FixtureDraftBackend
                        backend = FixtureDraftBackend(lease,SimpleNamespace(registered=True),stopped,
                            Observation.model_validate_json(json.dumps(target)),request["text"],title=request["title"],prefix=request["prefix"],host_pid=host_pid)
                    else:
                        backend = NotepadDraftBackend(lease, SimpleNamespace(registered=True), stopped,
                            Observation.model_validate_json(json.dumps(target)), request["text"]) if target else RegisteredSystemBackend(lease, SimpleNamespace(registered=True), stopped)
                    data = True
                elif operation == "seal":
                    import win32gui
                    target = Observation.model_validate_json(json.dumps(request["target"]))
                    sealed = target.model_copy(update={"document_digest": digest(win32gui.GetWindowText(target.hwnd).removeprefix("*"))})
                    probe = NotepadDraftBackend(lease, SimpleNamespace(registered=True), stopped, sealed, "x", sealing=True)
                    data = probe.observe_draft(require_focus=False).model_dump(mode="json")
                elif operation == "observe":
                    if not isinstance(backend, NotepadDraftBackend):
                        raise PolicyDenied("DRAFT_NOT_CONFIGURED")
                    data = backend.observe_draft(require_focus=request.get("require_focus", True)).model_dump(mode="json")
                elif operation == "read_text":
                    data = backend.read_text()
                elif operation == "watch":
                    expected = observe_window(backend.target.hwnd)
                    watcher = ContextWatchdog(expected, SimpleNamespace(trip=stopped.set))
                    watcher.start()
                    data = True
                elif operation == "test_wait" and "--test-mode" in sys.argv:
                    stopped.wait(60)
                    raise PolicyDenied("STOPPED")
                elif operation == "test_error" and "--test-mode" in sys.argv:
                    raise RuntimeError("DIAGNOSTIC_TOOL_ERROR")
                elif operation == "execute":
                    action = ACTION_SCHEMA.validate_json(json.dumps(request["action"]))
                    if action.task_id != first.task_id or action.generation != first.generation:
                        raise PolicyDenied("STALE_NATIVE_ACTION")
                    observed = Observation.model_validate_json(json.dumps(request["observation"]))
                    if not backend.permits(action) or stopped.is_set():
                        raise PolicyDenied("NATIVE_ACTION_DENIED")
                    backend.bind(observed)
                    backend.dispatch_notice = lambda phase, stamp, count: send({"event":"dispatch", "phase":phase,"perf":stamp,"count":count,"request":request_id})
                    data = backend.execute(action, stopped)
                else:
                    raise ProtocolError("unknown native operation")
                send({"request": request_id, "ok": True, "data": data})
            except (PolicyDenied, OSError, RuntimeError, comtypes.COMError) as exc:
                send({"request": request_id, "ok": False, "code": str(exc) if isinstance(exc, PolicyDenied) else "NATIVE_RESULT_UNKNOWN"})
        if monitor.changed.is_set() or watcher and watcher.reason:
            send({"event": "revoked", "code": monitor.reason or watcher.reason, "mono": time.monotonic()})
        return 0
    finally:
        ended.set()
        monitor.close()
        if watcher:
            watcher.close()
        lease.close()
        kernel.CloseHandle(parent_handle)
        stopped.close()
        comtypes.CoUninitialize()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError):
        raise SystemExit(2)
