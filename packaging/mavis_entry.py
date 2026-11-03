"""Shared frozen script; the companion console executable has a closed dispatcher."""
import os
from pathlib import Path
import sys

os.environ["ANONYMIZED_TELEMETRY"] = "false"
os.environ["DAFEIYU_MAVIS"] = "1"

if Path(sys.executable).name.lower() == "mavis-worker.exe":
    from assistant.distribution import helper_main
    raise SystemExit(helper_main())

if "--settings" in sys.argv:
    from pet.qt_plugin_sanitizer import sanitize_plugin_path
    sanitize_plugin_path()
    from pet.__main__ import _run_settings
    raise SystemExit(_run_settings())

from assistant.__main__ import main
raise SystemExit(main())
