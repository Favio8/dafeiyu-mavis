"""Local dependency/license/source inventory, containing no environment secrets."""
from __future__ import annotations

import hashlib
from importlib import metadata
import json
from pathlib import Path
import subprocess
import sys


def main() -> int:
    """Record installed packages and license metadata; do not infer missing asset rights."""
    root = Path(__file__).resolve().parents[1]
    evidence = root / ".scratch/m0-m1/evidence"
    entries = []
    for package in sorted(metadata.distributions(), key=lambda item: item.metadata["Name"].lower()):
        license_value = package.metadata.get("License-Expression") or package.metadata.get("License")
        license_files = [str(p) for p in package.files or [] if "license" in str(p).lower() or "copying" in str(p).lower()]
        entries.append({"name": package.metadata["Name"], "version": package.version,
                        "license_metadata": license_value, "license_files": license_files})
    (evidence / "runtime-dependencies.json").write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    import imageio_ffmpeg
    ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
    result = subprocess.run([str(ffmpeg), "-L"], capture_output=True, timeout=15)
    (evidence / "ffmpeg-license.txt").write_bytes(result.stdout + result.stderr)
    print(json.dumps({"packages": len(entries), "python": sys.version.split()[0], "ffmpeg": ffmpeg.name,
        "ffmpeg_sha256": hashlib.sha256(ffmpeg.read_bytes()).hexdigest(), "ffmpeg_license_exit": result.returncode}))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
