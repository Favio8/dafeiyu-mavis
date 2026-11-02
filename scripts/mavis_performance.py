"""Native residency measurement. Keep every sample; never accelerate elapsed time."""
from __future__ import annotations

import argparse
import cProfile
import importlib.metadata
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from collections import Counter, deque
from uuid import uuid4

_MODULE_STARTED = time.monotonic()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=28800)
    parser.add_argument("--warmup", type=int, default=600)
    parser.add_argument("--voice-models", type=Path)
    parser.add_argument("--voice-child", action="store_true")
    parser.add_argument("--core-only", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--parent-pid",type=int)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    if args.voice_child:
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        parent=kernel.OpenProcess(0x100000,False,args.parent_pid)
        if not parent:return 2
        import numpy as np
        from assistant.voice_engine import VoiceEngine
        engine = VoiceEngine(args.voice_models.resolve(), lambda *_: None)
        engine.arm()
        print("VOICE_MODELS_LOADED_SYNTHETIC_SILENCE", flush=True)
        deadline = time.monotonic()+args.seconds+60
        while time.monotonic()<deadline:
            if kernel.WaitForSingleObject(parent,0)!=0x102:return 0
            start = time.monotonic()
            engine.feed(np.zeros(1600, np.float32))
            time.sleep(max(0, .1-(time.monotonic()-start)))
        return 0
    output = (args.output or root / ".scratch/m5/performance" / (str(time.time_ns())+"-"+uuid4().hex[:6])).resolve()
    output.mkdir(parents=True,exist_ok=True)
    if (output / "samples.jsonl").exists():
        raise ValueError("refusing to combine separate residency runs")
    profile = output / "profile"
    profile.mkdir()
    os.environ.update(DAFEIYU_MAVIS="1", MAVIS_DATA_HOME=str(profile), MAVIS_TEST_MODE="1", ANONYMIZED_TELEMETRY="false")
    os.environ.pop("QT_QPA_PLATFORM", None)
    from pet.qt_plugin_sanitizer import sanitize_plugin_path
    sanitize_plugin_path()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    import psutil
    from assistant.pet_bridge import PetBridge
    from assistant.controller import Controller
    process = psutil.Process()
    started = _MODULE_STARTED
    previous_beat = [started]
    beats = Counter()
    samples = deque(maxlen=60)
    baseline = []
    aggregate = {"steady_count":0,"cpu_sum":0.0,"peak_rss_mib":0.0,"samples":0}
    owned = {}
    cpu_previous = {}
    network = set()
    original_run = Controller.run
    def profiled_run(controller):
        profiler = cProfile.Profile()
        profiler.enable()
        try:
            original_run(controller)
        finally:
            profiler.disable()
            profiler.dump_stats(str(output / "controller.prof"))
    if args.profile:
        Controller.run = profiled_run
    ui_profile = cProfile.Profile()
    report = {"requested_seconds":args.seconds, "warmup_seconds":args.warmup, "source_root":str(root),
        "mode":"core-only" if args.core_only else "full upstream pet", "voice_source":"synthetic 16kHz silence, no microphone" if args.voice_models else "microphone off, no voice model loaded",
        "hardware":{"cpu_logical":psutil.cpu_count(), "cpu_physical":psutil.cpu_count(logical=False), "ram_bytes":psutil.virtual_memory().total},
        "versions":{name:importlib.metadata.version(name) for name in ["PySide6","sherpa-onnx","psutil"]},
        "excluded_housekeeping":["stale temp deletion", "autostart registry cleanup"], "errors":[]}
    report["profiling_enabled"] = args.profile
    if os.name == "nt":
        import winreg
        for path, name, key in [(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString", "cpu_model"), (r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "CurrentBuildNumber", "windows_build")]:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as handle:
                report["hardware"][key] = winreg.QueryValueEx(handle, name)[0]
    voice = None
    voice_log = None
    if args.voice_models:
        env = {k:v for k,v in os.environ.items() if k.upper() in {"SYSTEMROOT","WINDIR","PATH","TEMP","TMP","LOCALAPPDATA","APPDATA","USERPROFILE"}}
        env.update(PYTHONUTF8="1",ANONYMIZED_TELEMETRY="false")
        voice_log = (output / "voice-child.txt").open("w", encoding="utf-8")
        voice = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--voice-child", "--parent-pid",str(os.getpid()), "--voice-models", str(args.voice_models.resolve()), "--seconds", str(args.seconds)], env=env, stdout=voice_log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
    def heartbeat():
        now = time.monotonic()
        beats[round((now-previous_beat[0])*1000)] += 1
        previous_beat[0] = now
    def sample():
        now = time.monotonic()
        total_rss = total_handles = total_threads = 0
        cpu_machine = 0.0
        processes=[]
        for item in [process, *process.children(recursive=True)]:
            try:
                identity = (item.pid, item.create_time())
                cpu = item.cpu_times()
                current = cpu.user+cpu.system
                part_cpu=None
                if identity in cpu_previous:
                    old_time, old_cpu = cpu_previous[identity]
                    part_cpu=100*(current-old_cpu)/(now-old_time)/(psutil.cpu_count() or 1)
                    cpu_machine += part_cpu
                cpu_previous[identity] = (now, current)
                rss=item.memory_info().rss
                total_rss += rss
                processes.append({"pid":item.pid,"name":item.name(),"rss_mib":rss/1024**2,"cpu_machine_percent":part_cpu})
                total_handles += item.num_handles() if os.name=="nt" else item.num_fds()
                total_threads += item.num_threads()
                for conn in item.net_connections(kind="inet"):
                    if conn.raddr:
                        network.add((item.name(), conn.raddr.ip, conn.raddr.port))
            except psutil.Error:
                continue
        pet_visible = None
        if owned.get("shell"):
            from pet.multi_window_shared import presentation_targets
            from PySide6.QtWidgets import QWidget
            from PySide6.QtGui import QImage
            widgets = [target if isinstance(target,QWidget) else getattr(target,"overlay",None) for target in presentation_targets(owned["shell"])]
            widgets = [widget for widget in widgets if widget is not None and widget.isVisible()]
            pet_visible = bool(widgets)
            if "first_pet_pixels_ms" not in report:
                for widget in widgets:
                    frame = widget.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
                    data = bytes(frame.constBits())
                    if any(data[3::4]):
                        report["first_pet_pixels_ms"] = (time.monotonic()-started)*1000
                        break
        row = {"elapsed_s":now-started,"rss_mib":total_rss/1024**2,"handles":total_handles,"threads":total_threads,"cpu_machine_percent":cpu_machine,"pet_visible":pet_visible,"processes":processes}
        samples.append(row)
        aggregate["samples"] += 1
        aggregate["peak_rss_mib"] = max(aggregate["peak_rss_mib"],row["rss_mib"])
        if row["elapsed_s"] >= args.warmup:
            aggregate["steady_count"] += 1
            aggregate["cpu_sum"] += row["cpu_machine_percent"]
            if len(baseline)<60:
                baseline.append(row)
        with (output / "samples.jsonl").open("a",encoding="utf-8") as file:
            file.write(json.dumps(row)+"\n")
        (output / "progress.json").write_text(json.dumps({"requested_seconds":args.seconds,"elapsed_s":row["elapsed_s"],"completed":False,"last_sample":row}),encoding="utf-8")
        if voice and voice.poll() is not None:
            report["errors"].append("VOICE_BENCH_WORKER_EXITED")
            QApplication.instance().quit()
        if owned["bridge"].stop.event.is_set():
            report["errors"].append("USER_OR_SAFETY_STOP")
            QApplication.instance().quit()
        if now-started>=args.seconds:
            QApplication.instance().quit()
    def setup(app, bridge):
        owned["bridge"] = bridge
        bridge.window.hide()
        report["startup_to_host_ms"] = (time.monotonic()-started)*1000
        report["screens"] = [{"geometry":s.geometry().getRect(),"dpr":s.devicePixelRatio(),"logical_dpi":s.logicalDotsPerInch()} for s in app.screens()]
        beat = QTimer(app)
        beat.setInterval(50)
        beat.timeout.connect(heartbeat)
        beat.start()
        tick = QTimer(app)
        tick.setInterval(1000)
        tick.timeout.connect(sample)
        tick.start()
        owned.update(beat=beat,tick=tick)
        sample()
    if args.profile:
        ui_profile.enable()
    if args.core_only:
        from types import SimpleNamespace
        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)
        bridge = PetBridge(app, None, SimpleNamespace(dir=profile))
        setup(app,bridge)
        code = app.exec()
        bridge.close()
    else:
        from pet import app as pet_app
        original_start = pet_app.AppShell.start
        def wrapped_start(shell):
            original_start(shell)
            owned["shell"] = shell
            QTimer.singleShot(0,lambda:setup(shell.app,shell.mavis))
        pet_app.AppShell.start = wrapped_start
        pet_app._cleanup_stale_runtime_dirs = lambda:None
        pet_app.autostart_mod.cleanup_stale_entries = lambda:0
        code = pet_app.main(["mavis-performance"],enable_chat=False)
    if args.profile:
        ui_profile.disable()
        ui_profile.dump_stats(str(output / "ui.prof"))
    elapsed = time.monotonic()-started
    if voice:
        voice.terminate()
        voice.wait(timeout=5)
        voice_log.close()
    stable = [row for row in samples if row["elapsed_s"]>=args.warmup]
    def p95(values):
        at = 0
        for value, count in sorted(values.items()):
            at += count
            if at >= sum(values.values())*.95:
                return value
        return None
    growth = None
    if len(stable)>=2:
        first = statistics.median(r["rss_mib"] for r in baseline)
        last = statistics.median(r["rss_mib"] for r in stable[-min(60,len(stable)):])
        growth = (last-first)/first if first else None
    report.update(exit_code=code,elapsed_s=elapsed,completed=elapsed>=args.seconds and not report["errors"],
        peak_rss_mib=aggregate["peak_rss_mib"],steady_mean_cpu=aggregate["cpu_sum"]/aggregate["steady_count"] if aggregate["steady_count"] else None,
        samples=aggregate["samples"],heartbeat_p95_ms=p95(beats),memory_growth_fraction=growth,
        network_connections_observed=sorted(network), sampling_limit="1s process/connection snapshots; exited child CPU and brief native connections may be missed",
        thresholds={"steady_rss_mib":650,"peak_rss_mib":1536,"cpu_machine_percent":5 if args.voice_models else 2,"memory_growth_fraction":.10,"required_residency_seconds":28800},
        acceptance="pending: duration/hardware matrix and real microphone not replaced by a short or synthetic source run")
    (output / "result.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("evidence="+str(output),flush=True)
    return code if report["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
