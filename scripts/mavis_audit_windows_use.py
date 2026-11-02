"""Audit installed Windows-Use, with shell/network blocked before its first import."""
from __future__ import annotations

import ast
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import sys
import types


def main() -> int:
    """Report actual wheel API and exercise primitive interception with inert stand-ins."""
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    profile = root / ".scratch/m0-m1/audit-profile"
    profile.mkdir(parents=True, exist_ok=True)
    for key in ("APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOME", "TEMP", "TMP"):
        os.environ[key] = str(profile)
    os.environ["ANONYMIZED_TELEMETRY"] = "false"
    os.chdir(profile)
    attempts = []

    def guard(event, args):
        if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
            attempts.append(event)  # No URL, command or credential is recorded.
            raise PermissionError("M0 audit denies network and subprocesses")
    sys.addaudithook(guard)
    import dotenv
    dotenv.load_dotenv = lambda *args, **kwargs: False  # Do not search unrelated user .env files.
    distribution = metadata.distribution("windows-use")
    package = Path(distribution.locate_file("windows_use"))
    files = ["__init__.py", "agent/service.py", "agent/tools/service.py", "agent/desktop/service.py", "telemetry/service.py", "tools/service.py", "uia/__init__.py"]
    report = {"version": distribution.version, "python": sys.version.split()[0], "files": {}, "network_or_shell_attempts": attempts}
    for relative in files:
        path = package / relative
        report["files"][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    source = (package / "agent/desktop/service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    desktop = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Desktop")
    report["desktop_methods"] = [node.name for node in desktop.body if isinstance(node, ast.FunctionDef)]
    report["command_callers"] = [node.name for node in desktop.body if isinstance(node, ast.FunctionDef)
        and any(isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "execute_command" for call in ast.walk(node))]
    from windows_use.agent.desktop.service import Desktop
    from windows_use.telemetry.service import ProductTelemetry
    telemetry = ProductTelemetry()
    telemetry.capture(types.SimpleNamespace(event_name="mavis_audit", properties={}))
    telemetry.flush()
    report["telemetry_disabled"] = telemetry.client is None and telemetry._user_id is None
    # Exercise the actual installed method bodies against an inert primitive object.
    # One top-level type call reaches a click and then SendKeys: the second primitive
    # must require its own permission. This is not a Windows input acceptance test.
    calls = []
    class GuardedPrimitives:
        def __getattr__(self, name):
            def invoke(*args, **kwargs):
                calls.append(name)
                if len(calls) > 1:
                    raise PermissionError("second primitive needs a new permit")
            return invoke
    method = next(node for node in desktop.body if isinstance(node, ast.FunctionDef) and node.name == "type")
    module = ast.Module(body=[method], type_ignores=[])
    scope = {"uia": GuardedPrimitives(), "Literal": __import__("typing").Literal,
             "escape_text_for_sendkeys": lambda text: text, "sleep": lambda value: None}
    exec(compile(ast.fix_missing_locations(module), "<audited Desktop.type body>", "exec"), scope)
    try:
        scope["type"](None, (0, 0), "fixture", press_enter="true")
    except PermissionError:
        pass
    report["top_level_type_primitive_trace"] = calls
    report["per_primitive_denial_verified_with_inert_backend"] = calls == ["Click", "SendKeys"]
    report["real_input"] = "not invoked"
    # A real UIA lookup of our own Qt window, never another application's content.
    from PySide6.QtWidgets import QApplication, QLineEdit
    import windows_use.uia as uia
    app = QApplication([])
    widget = QLineEdit("Mavis audit fixture")
    widget.setWindowTitle("Mavis audit fixture")
    widget.show()
    app.processEvents()
    control = uia.ControlFromHandle(int(widget.winId()))
    report["uia_own_window"] = {"pid_matches": control.ProcessId == os.getpid(), "title_matches": control.Name == "Mavis audit fixture"}
    widget.close()
    report["desktop_constructible"] = isinstance(Desktop(use_vision=False), Desktop)
    output = root / ".scratch/m0-m1/evidence/windows-use-audit.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["telemetry_disabled"] and report["uia_own_window"]["pid_matches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
