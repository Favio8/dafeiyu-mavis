"""Exercise shipped executables, never substitute the source interpreter for the app."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time


def fixture_server():
    """A real local page with randomized layout; its state API is read-only for oracles."""
    states = {}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            from urllib.parse import urlsplit, parse_qs
            parsed = urlsplit(self.path)
            if parsed.path == "/state":
                data = json.dumps(states).encode()
                content = "application/json"
            else:
                seed = parse_qs(parsed.query).get("seed", ["0"])[0]
                page = """<!doctype html><meta charset=utf-8><title>Mavis benchmark fixture</title>
<style>body{font:18px sans-serif;margin:36px;background:#eef5ff}button,input,select{padding:10px;margin:8px}article{height:500px}</style>
<h1>Mavis isolated fixture</h1><label>搜索<input id=q aria-label=搜索></label><button onclick="eventOf('search',q.value);results.textContent=q.value">搜索</button>
<button onclick="panel.hidden=false;eventOf('panel',true)">详细信息</button><section id=panel hidden>本轮编号：<b id=number></b></section>
<label><input id=only type=checkbox onchange="eventOf('documents',this.checked)">仅显示文档</label>
<label>类别<select onchange="eventOf('category',this.value)"><option>全部</option><option>教程</option><option>新闻</option></select></label>
<div id=results></div><article>滚动后的目标在下面</article><div>本轮目标结果</div><button onclick="eventOf('page',2)">第二页</button>
<form onsubmit="event.preventDefault();eventOf('submit',true)"><label>姓名<input oninput="eventOf('draft_name',this.value)"></label><label>备注<input oninput="eventOf('draft_note',this.value)"></label><button>提交</button></form>
<button id=delayed disabled onclick="content.hidden=false;eventOf('delayed_content',true)">等待后打开内容</button><p id=content hidden>延迟内容已打开</p>
<canvas id=canvas width=600 height=140></canvas>
<script>
const seed=SEED;number.textContent='N'+seed;document.body.style.paddingLeft=(Number(seed)%170)+'px';q.setAttribute('aria-label',['搜索','查找','关键词'][Number(seed)%3]);only.checked=Boolean(Number(seed)%2);
function eventOf(name,value){fetch('/event',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({seed,name,value})})}
setTimeout(()=>delayed.disabled=false,500+Number(seed)%2501);
const c=canvas.getContext('2d'),x=25+Number(seed)%260;c.fillStyle='#2167d9';c.fillRect(x,30,140,55);c.fillStyle='white';c.fillText('低风险测试按钮',x+12,62);
canvas.onclick=e=>{const b=canvas.getBoundingClientRect();if(e.clientX-b.left>=x&&e.clientX-b.left<=x+140&&e.clientY-b.top>=30&&e.clientY-b.top<=85)eventOf('canvas',true)};
</script>""".replace("SEED", json.dumps(seed))
                data, content = page.encode("utf-8"), "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def do_POST(self):
            if self.path != "/event":
                self.send_error(404)
                return
            data = json.loads(self.rfile.read(min(4096, int(self.headers.get("Content-Length", "0")))))
            states.setdefault(str(data["seed"]), {}).setdefault("events", []).append({"name": data["name"], "value": data["value"]})
            self.send_response(204)
            self.end_headers()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, name="mavis-fixture", daemon=True).start()
    return server, states


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", type=Path)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=600)
    parser.add_argument("--probes-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be a new directory; existing evidence is preserved")
    args.output.mkdir(parents=True)
    helper = args.app_dir.resolve() / "mavis-worker.exe"
    if not helper.is_file():
        parser.error("the installed companion executable was not found")
    env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP", "LOCALAPPDATA", "APPDATA", "USERPROFILE"}}
    env.update(PATH=str(Path(os.environ["SYSTEMROOT"]) / "System32"), PYTHONUTF8="1", PYTHONIOENCODING="utf-8", ANONYMIZED_TELEMETRY="false")
    probes = []
    for kind in ["runtime", "vault", "security", *(["voice"] if args.models else []), *(["provider"] if args.allow_network else [])]:
        report = args.output / (kind+".json")
        command = [str(helper), *(["--security-suite"] if kind == "security" else ["--probe", kind]), "--output", str(report.resolve())]
        if kind == "voice":
            command += ["--models", str(args.models.resolve())]
        if kind == "provider":
            command.append("--allow-network")
        with (args.output / (kind+".txt")).open("x", encoding="utf-8") as file:
            file.write("COMMAND="+json.dumps(command)+"\n")
            file.flush()
            try:
                process = subprocess.run(command, env=env, cwd=args.app_dir, stdout=file, stderr=subprocess.STDOUT, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
                code = process.returncode
            except subprocess.TimeoutExpired:
                code = 124
            file.write("\nEXIT_CODE="+str(code)+"\n")
        probes.append({"kind": kind, "exit_code": code, "report_exists": report.is_file()})
        print(json.dumps({"probe": kind, "exit_code": code}), flush=True)
    if not args.probes_only:
        server, states = fixture_server()
        target = args.output / "computer-use.json"
        command = [str(helper), "--benchmark", "--output", str(target.resolve()), "--data-home", str((args.output / "profile").resolve()),
                   "--fixture-url", "http://127.0.0.1:"+str(server.server_port)+"/", "--wait-seconds", str(args.wait_seconds)]
        with (args.output / "computer-use.txt").open("x", encoding="utf-8") as file:
            file.write("COMMAND="+json.dumps(command)+"\n")
            file.flush()
            process = subprocess.Popen(command, env=env, cwd=args.app_dir, stdout=file, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                started = time.monotonic()
                announced = False
                while process.poll() is None:
                    ready = target.with_suffix(".ready.json")
                    if ready.is_file() and not announced:
                        print(json.dumps({"phase": "local_physical_hotkey_and_scope_required", "ready": str(ready), "instructions": "Ctrl+Alt+F11; reset in installed control center; enable the session-only Notepad scope. No synthetic physical confirmation."}), flush=True)
                        announced = True
                    if time.monotonic()-started > args.wait_seconds+3600:
                        process.terminate()
                        break
                    time.sleep(.5)
                process.wait(timeout=10)
                file.write("\nEXIT_CODE="+str(process.returncode)+"\n")
            finally:
                server.shutdown()
                server.server_close()
                (args.output / "fixture-state.json").write_text(json.dumps(states, indent=2), encoding="utf-8")
    summary = {"app_dir": str(args.app_dir.resolve()), "product_executable": str(helper), "product_uses_developer_python": False,
               "runner_python": sys.executable, "probes": probes, "computer_use_report": "computer-use.json" if not args.probes_only else None,
               "fresh_windows_user_or_vm": "pending; PATH isolation does not substitute for a clean machine", "voice_hardware_benchmark": "pending"}
    (args.output / "run.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"evidence": str(args.output.resolve()), "release_gate": "not_passed"}), flush=True)
    positive = True
    if not args.probes_only:
        positive = target.is_file() and json.loads(target.read_text(encoding="utf-8")).get("passed", False)
    return 0 if positive and all(p["exit_code"] == 0 for p in probes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
