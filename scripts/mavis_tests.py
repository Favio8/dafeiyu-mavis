"""Run pytest in a private workspace profile; never replace the user's profile."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time


def main() -> int:
    """Invoke pytest with bounded runtime and keep raw output plus exit code."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="m1-tests")
    parser.add_argument("--timeout", type=int, default=1200)
    args, tests = parser.parse_known_args()
    root = Path(__file__).resolve().parents[1]
    if not args.name.replace("-", "").isalnum():
        parser.error("name must be alphanumeric")
    base = root / ".scratch" / "m0-m1"
    sandbox = base / "profiles" / (args.name + "-" + str(time.time_ns()))
    sandbox.mkdir(parents=True)
    env = os.environ.copy()
    for key in ("APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOME", "TEMP", "TMP"):
        env[key] = str(sandbox)
    env.update(QT_QPA_PLATFORM="offscreen", PYTHONUTF8="1", ANONYMIZED_TELEMETRY="false",
               PYTHON_KEYRING_BACKEND="keyring.backends.fail.Keyring")
    diagnostic = base / "evidence" / (args.name + "-diagnostic")
    diagnostic.mkdir(parents=True, exist_ok=True)
    env["DSPET_TEST_DIAG_DIR"] = str(diagnostic)
    env.pop("DAFEIYU_MAVIS", None)
    # On Windows, System32/bash.exe can be a WSL stub without a distribution.
    # Prefer the already-installed Git Bash for upstream's read-only `bash -n` checks.
    import shutil
    git = shutil.which("git")
    if git:
        git_bin = Path(git).parent.parent / "bin"
        if (git_bin / "bash.exe").is_file():
            env["PATH"] = str(git_bin) + os.pathsep + env.get("PATH", "")
    log = base / "evidence" / (args.name + ".txt")
    log.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "pytest", *(tests or ["tests/mavis", "-q"]), "--basetemp", str(sandbox / "pytest")]
    start = time.monotonic()
    with log.open("w", encoding="utf-8") as output:
        output.write("COMMAND: " + repr(command) + "\nPROFILE: " + str(sandbox) + "\n")
        output.flush()
        process = subprocess.Popen(command, cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT)
        try:
            code = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            code = 124
        output.write(f"\nEXIT_CODE={code}\nELAPSED_S={time.monotonic()-start:.3f}\n")
    print(f"exit={code} evidence={log}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
