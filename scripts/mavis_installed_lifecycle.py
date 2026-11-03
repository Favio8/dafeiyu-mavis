"""Read-only startup oracle and normal WM_QUIT for only the app this script starts."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import time

import psutil
import win32gui
import win32process


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True)
    executable = args.app_dir.resolve() / "DaFeiYuMavis.exe"
    env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP", "LOCALAPPDATA", "APPDATA", "USERPROFILE"}}
    env.update(PATH=str(Path(os.environ["SYSTEMROOT"]) / "System32"), PYTHONUTF8="1", ANONYMIZED_TELEMETRY="false")
    output = (args.output / "startup.txt").open("x", encoding="utf-8")
    start = time.monotonic()
    process = subprocess.Popen([str(executable)], cwd=args.app_dir, env=env, stdout=output, stderr=subprocess.STDOUT)
    owner = psutil.Process(process.pid)
    birth = owner.create_time()
    windows = []
    main_thread = None
    while process.poll() is None and time.monotonic()-start < 40:
        windows = []
        def visit(hwnd, _):
            thread, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == process.pid and win32gui.IsWindowVisible(hwnd):
                windows.append({"hwnd": hwnd, "thread": thread, "title": win32gui.GetWindowText(hwnd), "bounds": win32gui.GetWindowRect(hwnd)})
        win32gui.EnumWindows(visit, None)
        center = next((w for w in windows if "控制中心" in w["title"]), None)
        if center:
            main_thread = center["thread"]
            break
        time.sleep(.2)
    observed = time.monotonic()-start
    second_code = None
    if main_thread:
        second = subprocess.run([str(executable)], cwd=args.app_dir, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=15)
        second_code = second.returncode
        time.sleep(2)
    # The target is the exact process launched above, with unchanged image/birth.
    if process.poll() is None and main_thread and owner.create_time() == birth and Path(owner.exe()).resolve() == executable:
        ctypes.windll.user32.PostThreadMessageW(main_thread, 0x12, 0, 0)
    graceful = False
    try:
        process.wait(timeout=15)
        graceful = process.returncode == 0
    except subprocess.TimeoutExpired:
        if owner.create_time() == birth and Path(owner.exe()).resolve() == executable:
            process.terminate()
            process.wait(timeout=5)
    output.close()
    report = {"passed": bool(main_thread) and second_code == 0 and graceful, "executable": str(executable),
              "pid": process.pid, "visible_own_windows": windows, "startup_to_control_center_s": observed,
              "second_instance_exit_code": second_code, "normal_wm_quit": graceful, "exit_code": process.returncode,
              "developer_python_in_product_path": False, "PATH": env["PATH"], "fresh_windows_vm": "pending"}
    (args.output / "lifecycle.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "evidence": str(args.output)}, ensure_ascii=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
