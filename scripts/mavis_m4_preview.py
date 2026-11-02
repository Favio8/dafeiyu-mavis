"""Open the actual control center in a fresh profile; optional own-window captures.

No fixture task data, microphone, API probes or desktop input is generated.
"""
import argparse
import json
from pathlib import Path
import sys
import time
import sqlite3
import os
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--database", type=Path, help="copy an existing real database into the isolated preview profile")
    parser.add_argument("--test-mode", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from pet.qt_plugin_sanitizer import sanitize_plugin_path
    sanitize_plugin_path()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from assistant.pet_bridge import PetBridge
    output = root / ".scratch/m4" / str(time.time_ns())
    output.mkdir(parents=True)
    profile = output / "profile"
    profile.mkdir()
    if args.database:
        with sqlite3.connect(args.database.resolve().as_uri()+"?mode=ro", uri=True) as source, sqlite3.connect(profile / ("state-test.db" if args.test_mode else "state.db")) as destination:
            source.backup(destination)
    os.environ["MAVIS_TEST_MODE"] = "1" if args.test_mode else "0"
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    bridge = PetBridge(app, None, SimpleNamespace(dir=profile))
    captures = [(1100, 0, "overview"), (720, 1, "history"), (560, 6, "privacy")]
    observed = []
    def capture(index=0):
        if index >= len(captures):
            app.quit()
            return
        width, page, name = captures[index]
        bridge.window.resize(width, 720)
        bridge.window.nav.setCurrentRow(page)
        if page == 1 and bridge.window.history.topLevelItemCount():
            bridge.window.history.setCurrentItem(bridge.window.history.topLevelItem(0))
        def save():
            bridge.window.grab().save(str(output / (name+".png")))
            observed.append({"page": page, "requested_width": width, "actual_width": bridge.window.width(), "sidebar_width": bridge.window.sidebar.width(), "real_task_count": bridge.window.latest["counts"]["tasks"] if bridge.window.latest else None})
            capture(index+1)
        QTimer.singleShot(200, save)
    if args.capture:
        QTimer.singleShot(800, capture)
    result = app.exec()
    bridge.close()
    (output / "preview.json").write_text(json.dumps({"platform": app.platformName(), "captures": observed, "source": "copied real database" if args.database else "new empty database", "purpose": "actual widgets and committed records; functional acceptance deferred"}, indent=2), encoding="utf-8")
    print("preview="+str(output))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
