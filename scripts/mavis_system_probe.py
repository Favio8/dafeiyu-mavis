"""Explicit real L1 acceptance: gateway -> fixed Notepad launch -> independent window oracle."""
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from assistant.actions import LaunchApp
from assistant.contracts import Goal, TaskStatus as S
from assistant.gateway import ToolGateway
from assistant.policy import Policy, Scope
from assistant.service import TaskService
from assistant.stop import StopController, EmergencyHotkey
from assistant.storage import Store
from assistant.system_backend import RegisteredSystemBackend, notepad_windows
from assistant.verifier import Expected, verify_window
from assistant.windows_observer import DesktopLease, observe_window


def main() -> int:
    """Leave the opened app alone; never close user windows or alter documents/files."""
    import win32gui
    import ctypes
    if ctypes.windll.shell32.IsUserAnAdmin():
        raise SystemExit("NON_ADMIN_REQUIRED")
    stop = StopController()
    hotkey = EmergencyHotkey(stop)
    lease = DesktopLease()
    store = None
    run = ROOT / ".scratch/m2/evidence" / ("system-" + uuid4().hex[:8])
    run.mkdir(parents=True)
    try:
        if not hotkey.start() or not lease.acquire():
            raise RuntimeError("NATIVE_CONTROL_NOT_ARMED")
        before = notepad_windows()
        store = Store(run / "state.db")
        service = TaskService(store, stop=stop.event)
        backend = RegisteredSystemBackend(lease, hotkey, stop.event)
        gate = ToolGateway(service, Policy(Scope(enabled=True, apps=frozenset({"notepad.exe"}))), object(), backend)
        task = service.create("打开记事本（受控实机验收）", goals=(Goal(predicate="window", description="可观察的普通权限记事本窗口"),))
        service.transition(S.INTERPRETING)
        service.persist(service.task, "task.route", "deterministic")
        service.transition(S.EXECUTING)
        gate.observe(observe_window(win32gui.GetForegroundWindow()))
        action = LaunchApp(task_id=task.id, generation=task.generation, app_id="notepad.exe")
        permit = gate.propose(action)
        tool = gate.dispatch(permit.id, action)
        after = []
        deadline = time.monotonic() + 8
        while not stop.event.is_set() and time.monotonic() < deadline:
            after = notepad_windows()
            if after:
                break
            stop.event.wait(.1)
        if stop.event.is_set():
            service.cancel()
        else:
            service.finish([verify_window(service.task, Expected("primary", "window", "notepad.exe"), after[0] if after else None)])
        report = {"tool_status":tool.status, "status":service.task.status.value, "verification":service.task.verification_status,
                  "before_windows":len(before), "after_windows":len(after), "action_count":service.task.action_count,
                  "input_injection":False, "files_modified":False, "effects":"Notepad launch requested; opened window retained",
                  "events":[e.model_dump(mode="json") for e in store.events(task.id)]}
        (run / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k:v for k,v in report.items() if k != "events"}, ensure_ascii=False))
        print("evidence=" + str(run))
        return 0 if service.task.status == S.SUCCEEDED else 1
    finally:
        if store:
            store.close()
        lease.close()
        hotkey.close()


if __name__ == "__main__":
    raise SystemExit(main())
