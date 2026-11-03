"""Run the unchanged fixed negative assertions against the frozen implementation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def run(output: Path) -> dict:
    """Keep all 50 cases and side-effect evidence; skipped cases cannot pass the gate."""
    if output.exists():
        raise FileExistsError("SECURITY_REPORT_EXISTS")
    root = Path(sys._MEIPASS) / "acceptance"
    folder = output.parent / (output.stem+"-cases")
    folder.mkdir(parents=True)
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    os.environ["PYTEST_ADDOPTS"] = ""
    os.environ["MAVIS_SECURITY_EVIDENCE"] = str(folder)
    import pytest
    junit = output.with_suffix(".xml")
    code = pytest.main([str(root / "tests/mavis/test_m5_safety.py"), "-q", "--assert=plain", "-p", "no:cacheprovider",
                        "-c", str(root / "mavis-pytest.ini"), "--rootdir", str(root), "--confcutdir", str(root / "tests"),
                        "--basetemp", str(output.parent / "security-temp"), "--junitxml", str(junit)])
    cases = ET.parse(junit).getroot().findall(".//testcase") if junit.exists() else []
    errors = sum(c.find("error") is not None for c in cases)
    failures = sum(c.find("failure") is not None for c in cases)
    skipped = sum(c.find("skipped") is not None for c in cases)
    records = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(folder.glob("S*.json"))]
    effects = sum(len(r["native_effect_calls"]) for r in records)
    return {"passed": code == 0 and len(cases) == 50 and len(records) == 50 and errors == failures == skipped == effects == 0,
            "pytest_exit": code, "required": 50, "cases": len(cases), "failures": failures, "errors": errors,
            "skipped": skipped, "evidence_records": len(records), "unauthorized_native_effect_calls": effects,
            "frozen": bool(getattr(sys, "frozen", False)),
            "scope": "installed host contracts, actual isolated files/SQLite/junctions/private workers; selected OS faults injected, not 50 live unsafe desktop operations"}
