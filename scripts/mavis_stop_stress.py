"""20 actual Windows fixture-input/worker stop trials. No user document is used.

WM_HOTKEY is posted for repeatability: this is explicitly not a physical-key test.
Each text/focus action goes through the same one-use ToolGateway as product input.
"""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from uuid import uuid4

SCENARIOS = ("long_input", "model_wait", "page_wait", "tool_error")


def fixture(title):
    import win32api
    import win32con
    import win32gui
    instance = win32api.GetModuleHandle(None)
    cls = win32gui.WNDCLASS()
    cls.hInstance = instance
    cls.lpszClassName = "MavisPrivateStopFixture"
    started = False
    def window_proc(hwnd, message, wparam, lparam):
        nonlocal started
        if message == win32con.WM_COMMAND and wparam & 0xFFFF == 16 and wparam >> 16 == win32con.BN_CLICKED:
            if not started and win32gui.GetForegroundWindow() == hwnd:
                started = True
                win32gui.EnableWindow(lparam, False)
                ctypes.windll.user32.AllowSetForegroundWindow(-1)
                print(json.dumps({"started":True}),flush=True)
            return 0
        if message == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(hwnd,message,wparam,lparam)
    cls.lpfnWndProc = window_proc
    atom = win32gui.RegisterClass(cls)
    hwnd = win32gui.CreateWindowEx(0,atom,title,win32con.WS_OVERLAPPEDWINDOW|win32con.WS_VISIBLE,250,200,680,240,0,0,instance,None)
    win32gui.CreateWindowEx(0,"Static","Mavis: isolated stop test. Only m is typed. Ctrl+Alt+F11 stops.",win32con.WS_CHILD|win32con.WS_VISIBLE,20,20,620,40,hwnd,10,instance,None)
    field = win32gui.CreateWindowEx(0,"Edit","",win32con.WS_CHILD|win32con.WS_VISIBLE|win32con.WS_BORDER|win32con.ES_AUTOHSCROLL,20,80,620,40,hwnd,15,instance,None)
    win32gui.CreateWindowEx(0,"Button","START: keep this test window in foreground",win32con.WS_CHILD|win32con.WS_VISIBLE|win32con.BS_PUSHBUTTON,20,135,620,35,hwnd,16,instance,None)
    def read():
        while line := sys.stdin.readline():
            if line.strip() == "get":
                value = win32gui.GetWindowText(field)
                print(json.dumps({"text":value if all(c=="m" for c in value) else None}),flush=True)
            elif line.strip() == "quit":
                win32gui.PostMessage(hwnd,win32con.WM_CLOSE,0,0)
    threading.Thread(target=read,daemon=True).start()
    print(json.dumps({"hwnd":hwnd,"pid":os.getpid()}),flush=True)
    win32gui.PumpMessages()
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture")
    parser.add_argument("--wait-start",action="store_true")
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    if args.fixture:
        return fixture(args.fixture)
    if getattr(sys,"frozen",False) and args.output is None:
        parser.error("installed stop stress requires a new explicit --output directory")
    import win32gui
    from assistant.actions import FocusWindow,FocusControl,TypeText
    from assistant.contracts import Goal,TaskStatus as S,Budget
    from assistant.gateway import ToolGateway
    from assistant.native_session import NativeSession
    from assistant.policy import Policy,Scope,PolicyDenied
    from assistant.service import TaskService
    from assistant.storage import Store
    from assistant.stop import StopController,EmergencyHotkey
    from assistant.windows_observer import observe_window
    output=args.output or root / ".scratch/m5/stop-stress" / str(time.time_ns())
    output.mkdir(parents=True)
    title="Mavis safety fixture "+uuid4().hex
    env={k:v for k,v in os.environ.items() if k.upper() in {"SYSTEMROOT","SYSTEMDRIVE","WINDIR","PATH","TEMP","TMP","LOCALAPPDATA","APPDATA","USERPROFILE"}}
    env.update(PYTHONUTF8="1",ANONYMIZED_TELEMETRY="false")
    entry=[sys.executable,"--stop-stress"] if getattr(sys,"frozen",False) else [sys.executable,str(Path(__file__).resolve())]
    gui=subprocess.Popen([*entry,"--fixture",title],env=env,
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding="utf-8",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
    rows=[];setup_error=None
    gui_replies=queue.Queue()
    def replies():
        for line in gui.stdout:
            gui_replies.put(json.loads(line))
    threading.Thread(target=replies,daemon=True).start()
    def read_state():
        gui.stdin.write("get\n");gui.stdin.flush()
        value=gui_replies.get(timeout=3)["text"]
        if value is None:
            raise RuntimeError("USER_CHANGED_FIXTURE_TEXT")
        return value
    class Session(NativeSession):
        def __init__(self,*args):
            super().__init__(*args)
            self.first_input=threading.Event()
        def setup_extra(self):
            return {"fixture":True,"title":title,"prefix":self.initial_prefix}
        def _message(self,message):
            super()._message(message)
            if message.kind=="native_event":
                value=json.loads(message.payload)
                if value.get("event")=="dispatch" and value["phase"]=="returned" and value["count"]>0:
                    self.first_input.set()
    try:
        identity=gui_replies.get(timeout=10)
        if args.wait_start:
            if not gui_replies.get(timeout=600).get("started"):
                raise RuntimeError("FIXTURE_START_NOT_CONFIRMED")
        # Windows may refuse foreground activation; never type through that refusal.
        deadline=time.monotonic()+30
        while win32gui.GetForegroundWindow()!=identity["hwnd"] and time.monotonic()<deadline:
            time.sleep(.1)
        for trial in range(20):
            scenario=SCENARIOS[trial//5]
            row={"trial":trial+1,"scenario":scenario,"input_source":"posted WM_HOTKEY; not physical","passed":False,"dispatches":[]}
            stop=StopController();hotkey=EmergencyHotkey(stop,"Ctrl+Alt+F11")
            session=Session(stop,hotkey);session.test_mode=True
            service=TaskService(Store(output / f"trial-{trial+1}.db"),stop=stop.event)
            trigger=None
            try:
                row["phase"]="setup"
                if not hotkey.start(): raise RuntimeError(hotkey.error)
                prefix=read_state()
                task=service.create("native stop benchmark",mode="test",goals=(Goal(predicate="uia"),))
                service.persist(task.model_copy(update={"budget":Budget(actions=40,tools=120)}),"benchmark.budget","fixed PRD maximum action budget")
                service.transition(S.INTERPRETING);service.transition(S.EXECUTING)
                target=observe_window(identity["hwnd"])
                session.initial_prefix=prefix
                session.open(service.task,target=target,text=prefix+"m"*30)
                gate=ToolGateway(service,Policy(Scope(enabled=True,apps=frozenset({target.app}))),object(),session)
                def dispatch(action):
                    gate.observe(service.observation)
                    result=gate.dispatch(gate.propose(action).id,action)
                    row.setdefault("actions",[]).append({"tool":action.tool,"status":result.status,"error_code":result.error_code})
                    if result.status!="ok":raise PolicyDenied(result.error_code or "NATIVE_RESULT_UNKNOWN")
                    return result
                service.observation=target
                row["phase"]="focus_window"
                dispatch(FocusWindow(task_id=task.id,generation=task.generation,hwnd=target.hwnd))
                service.observation=session.observe_draft(require_focus=False)
                row["phase"]="focus_control"
                dispatch(FocusControl(task_id=task.id,generation=task.generation,control_id=service.observation.control_id))
                row["phase"]="confirm_focus"
                focus_until=time.monotonic()+1
                while True:
                    try:
                        session.observe_draft()
                        break
                    except PolicyDenied:
                        if stop.event.is_set() or time.monotonic()>=focus_until:
                            raise
                        time.sleep(.025)
                session.watch()
                row["phase"]=scenario
                user=ctypes.WinDLL("user32",use_last_error=True)
                def post():
                    row["worker_alive_at_post"]=not session.actual_exited()
                    row["latch_clear_at_post"]=not stop.event.is_set()
                    row["posted_perf"]=time.perf_counter()
                    user.PostThreadMessageW(hotkey.thread_id,0x312,hotkey.HOTKEY_ID,0)
                def trigger_stop():
                    if scenario=="long_input":
                        if not session.first_input.wait(5):
                            row["trigger_error"]="NO_ACTUAL_INPUT_TO_INTERRUPT"
                            return
                    else:
                        if stop.event.wait(.35):return
                    post()
                trigger=threading.Thread(target=trigger_stop,daemon=True);trigger.start()
                if scenario=="long_input":
                    for _ in range(30):
                        if stop.event.is_set():break
                        service.observation=session.observe_draft()
                        dispatch(TypeText(task_id=task.id,generation=task.generation,control_id=service.observation.control_id,text="m"))
                elif scenario=="page_wait":
                    session._call("test_wait")
                elif scenario=="tool_error":
                    try:session._call("test_error")
                    except RuntimeError:pass
                else:
                    from assistant.provider import DeepSeekProvider,ProviderSettings,ProviderError
                    client=DeepSeekProvider(ProviderSettings(),"canary")
                    async def hang(body):await asyncio.Event().wait()
                    client._request=hang
                    try:asyncio.run(client.complete([{"role":"user","content":"test"}],[],stop.event))
                    except ProviderError:pass
            except (PolicyDenied,RuntimeError,OSError,queue.Empty) as exc:
                row["error"]=str(exc)
            finally:
                if trigger:
                    trigger.join(timeout=6)
                    if row.get("posted_perf"):
                        stop.event.wait(max(0,1-(time.perf_counter()-row["posted_perf"])))
                if hotkey.received_perf is not None:
                    until=time.perf_counter()+1
                    while stop.last_stop_ms is None and time.perf_counter()<until:time.sleep(.001)
                    row["hotkey_received_perf"]=hotkey.received_perf
                    row["stop_handler_ms"]=stop.last_stop_ms
                    row["dispatches"]=list(session.dispatches)
                    late=[d["perf"] for d in session.dispatches if d["phase"]=="begin" and d["perf"]>hotkey.received_perf]
                    row["last_new_input_after_receive_ms"]=max([0,*[(stamp-hotkey.received_perf)*1000 for stamp in late]])
                    row["worker_exited"]=session.process is not None and session.actual_exited()
                    actual_packets = sum(d["phase"]=="returned" and d["count"]>0 for d in session.dispatches)
                    row["actual_input_packets"]=actual_packets
                    row["passed"]=row["worker_exited"] and row.get("worker_alive_at_post",False) and row.get("latch_clear_at_post",False) and (scenario!="long_input" or actual_packets>0) and stop.last_stop_ms is not None and stop.last_stop_ms<=1000 and row["last_new_input_after_receive_ms"]<=1000 and not stop.termination_errors
                row["atomic_packet_note"]="begin/returned markers are kept; in-flight native/OS packets are not claimed retracted"
                session.close();hotkey.close()
                row["revocation_code"]=session.revocation_code
                row["worker_failure"]=session.failure
                row["foreground_is_fixture"]=win32gui.GetForegroundWindow()==identity["hwnd"]
                after=read_state()
                time.sleep(.1)
                row["text_length_after_stop"]=len(after)
                row["text_stable_after_stop"]=after==read_state()
                row["passed"]=row["passed"] and row["text_stable_after_stop"] and after.startswith(prefix)
                service.check_timeouts();service.store.close()
                rows.append(row)
                (output / "progress.json").write_text(json.dumps({"requested_trials":20,"rows":rows},indent=2),encoding="utf-8")
            if not row["passed"]:
                break
            time.sleep(.15)
    except (queue.Empty,RuntimeError,OSError) as exc:
        setup_error="FIXTURE_START_OR_REPLY_TIMEOUT" if isinstance(exc,queue.Empty) else type(exc).__name__
    finally:
        try:
            gui.stdin.write("quit\n");gui.stdin.flush()
            gui.wait(timeout=2)
        except (OSError,subprocess.TimeoutExpired):
            import psutil
            if "identity" in locals():
                try:
                    actual=psutil.Process(identity["pid"])
                    if actual.name().lower()==Path(sys.executable).name.lower() and os.getpid() in {p.pid for p in actual.parents()}:
                        actual.terminate();actual.wait(timeout=2)
                except psutil.NoSuchProcess:pass
            if gui.poll() is None:gui.terminate()
            gui.wait(timeout=3)
    while len(rows)<20:
        rows.append({"trial":len(rows)+1,"scenario":SCENARIOS[len(rows)//5],"passed":False,"error":setup_error or "NOT_RUN_AFTER_SETUP_FAILURE"})
    result={"trials":rows,"passed_count":sum(row["passed"] for row in rows),"required":20,"physical_key_test":False,
        "setup_error":setup_error,
        "scope":"actual per-action gateway and SendInput in a private nonce-bound child fixture; network/page/tool faults injected",
        "passed":len(rows)==20 and all(row["passed"] for row in rows)}
    (output / "result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({"passed":result["passed"],"passed_count":result["passed_count"],"required":20,"evidence":str(output)}))
    return 0 if result["passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())
