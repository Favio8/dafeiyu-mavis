"""Run the fixed matrix through the installed Controller, retaining every denominator.

Only local UI can satisfy the normal physical-hotkey and scope prerequisites.
This module never grants permissions, approves R1 actions or completes GUI goals.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time


def run(args) -> int:
    if args.output.exists():
        raise FileExistsError("BENCHMARK_OUTPUT_EXISTS")
    home = args.data_home.resolve()
    profile = home / "DaFeiYuMavis"
    if (profile / "state.db").exists():
        raise ValueError("BENCHMARK_REQUIRES_FRESH_PROFILE")
    profile.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    os.environ.update(DAFEIYU_MAVIS="1", MAVIS_TEST_MODE="0", MAVIS_DATA_HOME=str(home), ANONYMIZED_TELEMETRY="false")
    from .settings import AppSettings, save_settings
    save_settings(profile / "assistant-settings.json", AppSettings(emergency_shortcut="Ctrl+Alt+F11", recording_shortcut="Ctrl+Alt+F10"))
    from pet.qt_plugin_sanitizer import sanitize_plugin_path
    sanitize_plugin_path()
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from pet.config import Config
    from .pet_bridge import PetBridge
    from .contracts import TERMINAL, TaskStatus
    from .system_backend import notepad_windows
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    bridge = PetBridge(app, None, Config())
    bridge.window.setWindowTitle("Mavis 0.1.0 · Installed Benchmark · Ctrl+Alt+F11")
    cases = json.loads((Path(__file__).with_name("assets") / "benchmark-cases.json").read_text(encoding="utf-8"))
    trials = [{**case, "repetition": repeat} for case in cases for repeat in (1, 2, 3)]
    synonyms = ["请帮我启动记事本", "麻烦开个记事本", "我想新建一份记事本文档", "调出一个空白记事本吧", "帮我打开哔哩哔哩首页", "用浏览器访问B站首页", "把测试笔记切到前面", "将笔记窗口放在屏幕左半边", "请仅勾选文档过滤项", "把网页里的当前编号抄进新笔记"]
    work = args.output.parent / "workspace"
    work.mkdir()
    (work / "已有 测试文件.txt").write_text("original benchmark fixture\n", encoding="utf-8")
    (work / "已有 测试文件.txt").chmod(0o400)
    baseline_hash = hashlib.sha256((work / "已有 测试文件.txt").read_bytes()).hexdigest()
    rows, extra = [], []
    state = {"active": None, "submitted": 0.0, "before": [], "owned": None, "started": None, "finished": False}
    waiting = time.monotonic()
    seed = random.SystemRandom().randrange(2**31)
    data = {"workspace": str(work), "file": str(work / "已有 测试文件.txt"),
            "newfile": str(work / "新结果 中文 空格.txt"), "url": args.fixture_url or "http://127.0.0.1:0/fixture-not-configured",
            "keyword": "mavis-"+str(seed), "replacement": "new draft "+str(seed)}
    ready = {"pid": os.getpid(), "executable": sys.executable, "frozen": bool(getattr(sys, "frozen", False)), "profile": str(profile),
             "instructions": "Physically press Ctrl+Alt+F11 in this installed benchmark. In the real control center reset stop, then enable the session-only Notepad scope. No permission is granted by the benchmark.",
             "planned": 90, "gui_required": 72, "seed": seed}
    args.output.with_suffix(".ready.json").write_text(json.dumps(ready, indent=2), encoding="utf-8")

    def record_progress():
        args.output.with_suffix(".progress.json").write_text(json.dumps({**ready, "completed_trials": len(rows), "generalization_trials": len(extra), "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    def finish(reason=None):
        if state["finished"]:
            return
        state["finished"] = True
        done = {(r["id"], r["repetition"]) for r in rows}
        for trial in trials:
            if (trial["id"], trial["repetition"]) not in done:
                rows.append({**trial, "status": "pending", "attempted": False, "error": reason or "NOT_RUN", "gui_exercised": False})
        success = sum(r["status"] == "passed" for r in rows)
        gui_success = sum(r["status"] == "passed" and r["gui_required"] for r in rows)
        fake = sum(r["status"] == "false_success" for r in rows)
        per_case = {c["id"]: sum(r["id"] == c["id"] and r["status"] == "passed" for r in rows) for c in cases}
        report = {**ready, "elapsed_s": time.monotonic()-waiting, "trials": rows, "generalization": extra,
                  "successes": success, "denominator": 90, "gui_successes": gui_success, "gui_denominator": 72,
                  "actual_gui_exercised": sum(r.get("gui_exercised", False) for r in rows),
                  "task_submissions": sum(r.get("attempted", False) for r in rows), "false_successes": fake, "per_case_successes": per_case,
                  "original_fixture_unchanged": hashlib.sha256((work / "已有 测试文件.txt").read_bytes()).hexdigest() == baseline_hash,
                  "thresholds": {"overall": 81, "gui": 65, "per_case": 2, "false_successes": 0},
                  "passed": success >= 81 and gui_success >= 65 and fake == 0 and all(n >= 2 for n in per_case.values()),
                  "operator_intervention": "local physical hotkey/reset/scope setup only; no target goals completed by operator",
                  "physical_hotkey_observed": bridge.hotkey.physical_seen, "local_scope_enabled": bridge.controller.native_enabled,
                  "all_gui_benchmark_completed": all(not r["gui_required"] or r.get("gui_exercised", False) for r in rows),
                  "voice_benchmark": {"status": "pending", "microphone": "not available", "positive_required": 200, "negative_hours_required": 10, "tts_minutes_required": 30, "commands_required": 200, "e2e_required": 60},
                  "scope": "installed Controller/TaskService/ToolGateway; unsupported routes are failures, not simulated success"}
        with args.output.open("x", encoding="utf-8") as file:
            json.dump(report, file, ensure_ascii=False, indent=2)
        bridge.window.exiting = True
        bridge.close()
        app.quit()

    def oracle(trial, before):
        if trial["id"] not in {"B03", "B07"}:
            return {"result": "not_measured", "reason": "GUI_OR_BROWSER_OR_FILE_BACKEND_NOT_IMPLEMENTED"}
        windows = notepad_windows()
        if trial["id"] == "B03":
            new = [w for w in windows if w.identity_digest not in {x.identity_digest for x in before}]
            if before or len(new) != 1:
                return {"result": "failed", "reason": "NO_UNIQUE_NEW_WINDOW"}
            state["owned"] = new[0]
            target = new[0]
        else:
            target = state["owned"]
            if target is None:
                return {"result": "not_measured", "reason": "NO_BENCHMARK_OWNED_DRAFT"}
        result = subprocess.run([sys.executable, "--probe", "uia", "--target", target.model_dump_json()], capture_output=True, text=True, encoding="utf-8", timeout=6, creationflags=subprocess.CREATE_NO_WINDOW)
        data = json.loads(result.stdout)
        if not data.get("passed"):
            return {"result": "unknown", "details": data}
        expected = "" if trial["id"] == "B03" else "你好，我是大肥鱼。"
        if data.get("pattern") == "text" and data["text"] in {expected+"\r", expected+"\n", expected+"\r\n"}:
            return {"result": "unknown", "reason": "ORACLE_PROVIDER_REQUIRES_CALIBRATION", "actual": data["text"], "expected": expected}
        return {"result": "passed" if data["text"] == expected else "failed", "method": data["method"], "actual": data["text"], "expected": expected}

    def tick():
        if state["finished"]:
            return
        try:
            controller = bridge.controller
            if not controller.ready.is_set():
                return
            if state["started"] is None:
                if controller.native_enabled and bridge.hotkey.physical_seen and not bridge.stop.event.is_set():
                    state["started"] = time.monotonic()
                elif time.monotonic()-waiting >= args.wait_seconds:
                    finish("PHYSICAL_HOTKEY_AND_LOCAL_SCOPE_NOT_CONFIRMED")
                return
            if state["active"]:
                current = controller.service.task
                if current is None or current.id == state.get("previous_task"):
                    return
                if current.status not in TERMINAL:
                    if time.monotonic()-state["submitted"] > 35:
                        bridge.stop.trip()
                    return
                trial = state["active"]
                if current.final_text != trial["command"]:
                    finish("UNEXPECTED_TASK_FROM_OPERATOR_NO_GOAL_ATTRIBUTION")
                    return
                details = controller.service.store.path
                import sqlite3
                with sqlite3.connect(details.resolve().as_uri()+"?mode=ro", uri=True) as connection:
                    steps = [json.loads(r[0]) for r in connection.execute("SELECT data FROM steps WHERE task_id=?", (str(current.id),))]
                    audit = {table: [json.loads(r[0]) for r in connection.execute("SELECT data FROM "+table+" WHERE task_id=?", (str(current.id),))] for table in ("events", "approvals", "verifications", "observations")}
                gateway = controller.native_tasks.gateway
                dispatches = list(getattr(gateway.backend, "dispatches", [])) if gateway and any(s.get("tool_name") == "desktop.type_text" for s in steps) else []
                gui = any(d.get("phase") == "returned" and d.get("count", 0) > 0 for d in dispatches)
                checked = oracle(trial, state["before"]) if current.status == TaskStatus.SUCCEEDED else {"result": "not_measured", "reason": current.error_code or current.status.value}
                verdict = "failed"
                if current.status == TaskStatus.SUCCEEDED:
                    verdict = "passed" if checked["result"] == "passed" and (not trial["gui_required"] or gui) else ("false_success" if checked["result"] == "failed" else "unverified")
                row = {**trial, "attempted": True, "task_id": str(current.id), "task": current.model_dump(mode="json"), "steps": steps, **audit,
                       "status": verdict, "scenario_validation_status": "verified" if verdict == "passed" else ("pending" if trial["gui_required"] and not gui else "failed_or_unverified"),
                       "oracle": checked, "gui_exercised": gui, "dispatches": dispatches, "error": current.error_code}
                (extra if trial["id"].startswith("G") else rows).append(row)
                state["active"] = None
                record_progress()
                if bridge.stop.event.is_set():
                    finish("STOP_LATCH_SET_NO_AUTOMATIC_RESET")
                return
            index = len(rows)
            if index < len(trials):
                trial = dict(trials[index])
            elif len(extra) < len(synonyms):
                trial = {"id": "G"+str(len(extra)+1).zfill(2), "repetition": 1, "command": synonyms[len(extra)], "gui_required": False}
            else:
                finish()
                return
            before = notepad_windows()
            if trial["id"] == "B03" and before:
                rows.append({**trial, "attempted": False, "status": "pending", "error": "INITIAL_NOTEPAD_NOT_CLOSED_NO_USER_WINDOW_TOUCHED", "gui_exercised": False})
                record_progress()
                return
            trial_seed = seed + index*101 + len(extra)
            trial["seed"] = trial_seed
            parameters = {**data, "keyword": "mavis-"+str(trial_seed), "replacement": "new draft "+str(trial_seed),
                          "newfile": str(work / (trial["id"]+"-"+str(trial["repetition"])+" 中文 新结果.txt")),
                          "url": data["url"]+("&" if "?" in data["url"] else "?")+"seed="+str(trial_seed)}
            trial["command"] = trial["command"].format(**parameters)
            state.update(active=trial, previous_task=controller.service.task.id if controller.service.task else None, submitted=time.monotonic(), before=before)
            controller.submit("record", trial["command"])
        except Exception as error:
            args.output.with_suffix(".error.json").write_text(json.dumps({"error": type(error).__name__, "phase": "benchmark_host", "message": str(error)[:160]}), encoding="utf-8")
            finish("BENCHMARK_HOST_ERROR_"+type(error).__name__)
    timer = QTimer(app)
    timer.setInterval(100)
    timer.timeout.connect(tick)
    timer.start()
    app.aboutToQuit.connect(lambda: finish("USER_EXITED_BENCHMARK"))
    app.exec()
    return 0 if json.loads(args.output.read_text(encoding="utf-8"))["passed"] else 1
