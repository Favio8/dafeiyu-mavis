"""Real Windows lease/hook/private-worker probe, deliberately dispatching no input."""
import ctypes
import json
from pathlib import Path
import sys
import time


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    from assistant.contracts import Task
    from assistant.native_session import NativeSession
    from assistant.stop import StopController, EmergencyHotkey
    from assistant.policy import PolicyDenied
    output = root / ".scratch/m5/native" / str(time.time_ns())
    output.mkdir(parents=True)
    stop = StopController()
    hotkey = EmergencyHotkey(stop, "Ctrl+Alt+F11")
    session = NativeSession(stop, hotkey)
    report = {"native_actions":0,"input_injected":False,"source":"real Windows mutex, low-level hooks and private subprocess; no GUI task"}
    try:
        if not hotkey.start():
            raise RuntimeError(hotkey.error)
        task = Task(original_text="read-only worker boundary probe",final_text="read-only worker boundary probe")
        session.open(task)
        report.update(worker_pid=session.peer_pid,ready=session.ready.is_set(),registered_hotkey=True)
        started = time.perf_counter()
        user = ctypes.WinDLL("user32",use_last_error=True)
        # An injected message tests actual WM_HOTKEY reception, never claims a
        # physical key press and never sends a Windows keyboard/mouse event.
        if not user.PostThreadMessageW(hotkey.thread_id,0x312,hotkey.HOTKEY_ID,0):
            raise RuntimeError("POST_HOTKEY_MESSAGE_FAILED")
        if not stop.event.wait(1):
            raise RuntimeError("STOP_DEADLINE_EXCEEDED")
        session.process.wait(timeout=1)
        while stop.last_stop_ms is None and time.perf_counter()-started<1:
            time.sleep(.001)
        report.update(stop_observed_ms=(time.perf_counter()-started)*1000,hotkey_received_mono=hotkey.received_mono,
            worst_stop_handler_ms=stop.last_stop_ms,worker_exited=session.actual_exited(),
            termination_errors=list(stop.termination_errors),injected_message=True)
        report["passed"] = report["worker_exited"] and report["stop_observed_ms"] <= 1000 and stop.last_stop_ms is not None and not stop.termination_errors
    except (RuntimeError,OSError,PolicyDenied) as exc:
        report.update(passed=False,error=str(exc))
    finally:
        session.close()
        hotkey.close()
    (output / "result.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({**report,"evidence":str(output)},indent=2))
    return 0 if report["passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())
