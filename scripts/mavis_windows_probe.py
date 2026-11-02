"""Read-only native observation + cross-process lease probe; never injects input."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from assistant.windows_observer import DesktopLease, input_desktop_is_default, observe_window


def main() -> int:
    """Use a private Qt window; do not enumerate or record unrelated user window text."""
    if "--lease-child" in sys.argv:
        lease = DesktopLease()
        held = lease.acquire()
        lease.close()
        print(json.dumps({"acquired": held}))
        return 0
    from pet.qt_plugin_sanitizer import sanitize_plugin_path
    sanitize_plugin_path()
    from PySide6.QtWidgets import QApplication, QLineEdit
    app = QApplication([])
    window = QLineEdit("Mavis read-only identity fixture")
    window.setWindowTitle("Mavis M2 observation probe")
    window.show()
    app.processEvents()
    observation = observe_window(int(window.winId()))
    lease = DesktopLease()
    command = [sys.executable, str(Path(__file__).resolve()), "--lease-child"]
    try:
        acquired = lease.acquire()
        blocked = subprocess.run(command, capture_output=True, text=True, timeout=10)
        lease.close()
        released = subprocess.run(command, capture_output=True, text=True, timeout=10)
        result = {"desktop_default": input_desktop_is_default(), "own_window_identified": observation.own_ui,
                  "integrity": observation.integrity, "dpi": observation.dpi, "bounds": observation.bounds,
                  "lease_acquired": acquired, "other_process_refused": not json.loads(blocked.stdout)["acquired"],
                  "other_process_after_release": json.loads(released.stdout)["acquired"],
                  "input_actions": 0, "user_window_text_read": False}
    finally:
        lease.close()
        window.close()
    output = ROOT / ".scratch/m2/evidence/windows-observer.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return 0 if all(result[k] for k in ("desktop_default", "own_window_identified", "lease_acquired", "other_process_refused", "other_process_after_release")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
