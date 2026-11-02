"""Real GUI pilot: a fresh empty Notepad, per-character grants, independent UIA oracle."""
import hashlib
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from assistant.actions import LaunchApp, FocusWindow, FocusControl, TypeText
from assistant.contracts import Goal, TaskStatus as S, TERMINAL
from assistant.gateway import ToolGateway
from assistant.notepad_backend import NotepadDraftBackend
from assistant.policy import Policy, Scope, PolicyDenied
from assistant.service import TaskService
from assistant.stop import StopController, EmergencyHotkey
from assistant.storage import Store
from assistant.system_backend import RegisteredSystemBackend, notepad_windows
from assistant.verifier import Expected, verify_text
from assistant.windows_observer import DesktopLease, observe_window, ContextWatchdog


def main(argv=None, stop_controller=None) -> int:
    """Never reuse a preexisting user document, save files or execute model-selected code."""
    import ctypes
    import win32gui
    import psutil
    if ctypes.windll.shell32.IsUserAnAdmin():
        raise SystemExit("NON_ADMIN_REQUIRED")
    proofs = sorted((ROOT / ".scratch/m2/evidence").glob("physical-stop-*.json"), key=lambda p:p.stat().st_mtime, reverse=True)
    if not proofs or proofs[0].stat().st_mtime < psutil.boot_time() or not json.loads(proofs[0].read_text())["passed"]:
        raise SystemExit("CURRENT_BOOT_PHYSICAL_STOP_VERIFICATION_REQUIRED")
    # Existing windows could contain user tabs, even when their current tab is blank.
    import argparse
    import re
    import sqlite3
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume-test-window")
    parser.add_argument("--wait-foreground", action="store_true")
    args = parser.parse_args(argv)
    existing = notepad_windows()
    resumed = None
    if args.resume_test_window:
        if not re.fullmatch(r"gui-[a-f0-9]{8}", args.resume_test_window):
            raise SystemExit("INVALID_TEST_RUN")
        previous = ROOT / ".scratch/m2/evidence" / args.resume_test_window
        with sqlite3.connect((previous / "state.db").as_uri() + "?mode=ro", uri=True) as db:
            records = [json.loads(row[0]) for row in db.execute("SELECT data FROM observations")]
        matches = [w for w in existing if any(r["app"]=="notepad.exe" and r["hwnd"]==w.hwnd and r["pid"]==w.pid for r in records)]
        if len(matches) != 1:
            raise SystemExit("TEST_WINDOW_IDENTITY_NOT_FOUND")
        resumed = matches[0]
    elif existing:
        raise SystemExit("PREEXISTING_NOTEPAD_REFUSED")
    run = ROOT / ".scratch/m2/evidence" / ("gui-" + uuid4().hex[:8])
    run.mkdir(parents=True)
    stop, lease = stop_controller or StopController(), DesktopLease()
    hotkey = EmergencyHotkey(stop)
    watcher = None
    store = Store(run / "state.db")
    service = TaskService(store, stop=stop.event)
    text = "你好，我是大肥鱼。"
    report = {"goal":text,"saved_files":False,"real_gui_input":True,"input_method":"Windows SendInput Unicode + independent UIA read",
              "physical_stop_proof":proofs[0].name}
    try:
        if not hotkey.start() or not lease.acquire():
            raise PolicyDenied("NATIVE_CONTROL_NOT_ARMED")
        task = service.create("在新空白测试记事本中输入：" + text, goals=(Goal(predicate="uia",description="UIA逐字读取与目标文本一致"),))
        service.transition(S.INTERPRETING)
        service.transition(S.EXECUTING)
        backend = RegisteredSystemBackend(lease, hotkey, stop.event)
        gate = ToolGateway(service, Policy(Scope(enabled=True,apps=frozenset({"notepad.exe"}))), object(), backend)
        if resumed is None:
            gate.observe(observe_window(win32gui.GetForegroundWindow()))
            launch = LaunchApp(task_id=task.id,generation=task.generation,app_id="notepad.exe")
            result = gate.dispatch(gate.propose(launch).id, launch)
            if result.status != "ok":
                raise PolicyDenied(result.error_code or "LAUNCH_FAILED")
        deadline = time.monotonic() + 8
        windows = notepad_windows()
        while not windows and time.monotonic() < deadline and not stop.event.is_set():
            stop.event.wait(.1)
            windows = notepad_windows()
        if len(windows) != 1:
            raise PolicyDenied("NEW_WINDOW_NOT_UNIQUE")
        target = windows[0]
        if args.wait_foreground:
            report["human_setup"] = "user brings the registered empty test Notepad to foreground"
            service.transition(S.WAITING_USER)
            until = time.monotonic() + 60
            while win32gui.GetForegroundWindow() != target.hwnd:
                if stop.event.wait(.05) or time.monotonic() >= until:
                    raise PolicyDenied("FOCUS_WAIT_CANCELLED_OR_TIMED_OUT")
            service.transition(S.INTERPRETING)
            service.transition(S.EXECUTING)
        draft = NotepadDraftBackend(lease, hotkey, stop.event, target, text)
        gate.backend = draft
        # The launch effect was independently observed. No old grant survives this boundary.
        service.observation = observe_window(target.hwnd)
        focus = FocusWindow(task_id=task.id,generation=task.generation,hwnd=target.hwnd)
        result = gate.dispatch(gate.propose(focus).id, focus)
        if result.status != "ok":
            raise PolicyDenied(result.error_code or "FOCUS_FAILED")
        if win32gui.GetForegroundWindow() != target.hwnd:
            raise PolicyDenied("FOCUS_NOT_VERIFIED")
        initial = draft.observe_draft(require_focus=False)  # refuses any nonempty or unrecognized document
        service.observation = initial
        focus_editor = FocusControl(task_id=task.id,generation=task.generation,control_id=initial.control_id)
        result = gate.dispatch(gate.propose(focus_editor).id, focus_editor)
        if result.status != "ok":
            raise PolicyDenied(result.error_code or "EDITOR_FOCUS_FAILED")
        until = time.monotonic() + 1
        while True:
            try:
                draft.observe_draft()
                break
            except PolicyDenied:
                if time.monotonic() >= until or stop.event.wait(.05):
                    raise
        report.update(hwnd=target.hwnd,pid=target.pid,initial_blank=True,control_id=initial.control_id)
        watcher = ContextWatchdog(observe_window(target.hwnd), stop)
        watcher.start()
        for character in text:
            if stop.event.is_set():
                service.cancel()
                break
            service.check_timeouts()
            if service.task.status in TERMINAL:
                break
            # Only verified expected-prefix edits advance the observation. User edits stop it.
            service.observation = draft.observe_draft()
            action = TypeText(task_id=task.id,generation=task.generation,control_id=service.observation.control_id,text=character)
            result = gate.dispatch(gate.propose(action).id, action)
            if result.status != "ok":
                break
            service.persist(service.task, "verification.step", "uia_prefix_sha256=" + hashlib.sha256(draft.read_text().encode()).hexdigest())
        if service.task.status not in TERMINAL:
            service.finish([verify_text(service.task, Expected("primary","uia",text), draft.read_text())])
        report.update(status=service.task.status.value,verification=service.task.verification_status,actions=service.task.action_count)
    except (PolicyDenied, OSError, RuntimeError) as exc:
        report["error_code"] = str(exc) if isinstance(exc,PolicyDenied) else type(exc).__name__
        if service.task and service.task.status not in TERMINAL:
            if stop.event.is_set():
                service.cancel()
            elif service.task.status in (S.EXECUTING,S.VERIFYING):
                service.finish([])
            else:
                service.transition(S.TIMED_OUT, error_code=report["error_code"])
        report["status"] = service.task.status.value if service.task else "NOT_STARTED"
    finally:
        if watcher:
            watcher.close()
        if service.task:
            report["events"] = [e.model_dump(mode="json") for e in store.events(service.task.id)]
        (run / "result.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        store.close()
        lease.close()
        hotkey.close()
    print(json.dumps({k:v for k,v in report.items() if k != "events"},ensure_ascii=False))
    print("evidence=" + str(run))
    return 0 if report["status"] == "SUCCEEDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
