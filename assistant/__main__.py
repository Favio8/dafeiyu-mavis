"""Independent Mavis entry; desktop presentation remains the upstream pet app."""
from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> int:
    """Launch a non-admin M1 host with isolated data and optional explicit test mode."""
    parser = argparse.ArgumentParser(description="DaFeiYu Mavis M0/M1 — real desktop input is disabled")
    parser.add_argument("--test-mode", action="store_true", help="use a separate test database and in-memory exercises")
    parser.add_argument("--data-home", type=Path, help="parent of the DaFeiYuMavis data namespace")
    parser.add_argument("--core-only", action="store_true", help="run only the core UI for diagnostics")
    args = parser.parse_args()
    os.environ["ANONYMIZED_TELEMETRY"] = "false"
    os.environ["DAFEIYU_MAVIS"] = "1"
    if args.data_home:
        os.environ["MAVIS_DATA_HOME"] = str(args.data_home.resolve())
    os.environ["MAVIS_TEST_MODE"] = "1" if args.test_mode else "0"
    if os.name == "nt":
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            raise SystemExit("Mavis requires a normal, non-administrator Windows session.")
    from pet.qt_plugin_sanitizer import sanitize_plugin_path
    sanitize_plugin_path()
    if args.core_only:
        from PySide6.QtWidgets import QApplication
        from pet.config import Config
        from .pet_bridge import attach
        from pet.overlay_instance_gate import acquire_overlay_instance_gate
        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)
        config = Config()
        gate = acquire_overlay_instance_gate(config.dir)
        if not gate.acquired:
            return 0
        try:
            host = attach(app, None, config)
            result = app.exec()
            host.close()
            return result
        finally:
            gate.release()
    from pet.app import main as pet_main
    return pet_main(["dafeiyu-mavis"], enable_chat=False)


if __name__ == "__main__":
    raise SystemExit(main())
