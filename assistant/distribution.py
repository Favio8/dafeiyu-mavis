"""Fixed frozen entry points. Worker selection never accepts an arbitrary module."""
from __future__ import annotations

import argparse
import importlib
from pathlib import Path
import sys

WORKERS = {"assistant.worker": "lifecycle", "assistant.native_worker": "native",
           "assistant.voice_worker": "voice", "assistant.model_probe_worker": "model"}
WORKER_EXE = "mavis-worker.exe"


def worker_command(module: str, *, test_mode: bool = False) -> list[str]:
    """Select a shipped worker; reject unknown modules before creating a process."""
    if module not in WORKERS:
        raise ValueError("UNREGISTERED_WORKER")
    command = [str(Path(sys.executable).with_name(WORKER_EXE)), "--worker", WORKERS[module]] if getattr(sys, "frozen", False) else [sys.executable, "-m", module]
    return command + (["--test-mode"] if test_mode else [])


def worker_executables() -> set[Path]:
    """Only the fixed installed helper may identify itself as a frozen worker."""
    if getattr(sys, "frozen", False):
        return {Path(sys.executable).with_name(WORKER_EXE).resolve()}
    return {Path(sys.executable).resolve(), Path(getattr(sys, "_base_executable", sys.executable)).resolve()}


def installed_data_home() -> Path | None:
    """Read an explicit portable marker or installer-written location, never old pet data."""
    if not getattr(sys, "frozen", False):
        return None
    folder = Path(sys.executable).parent
    if (folder / "portable.json").is_file():
        return folder / "data"
    location = folder / "mavis-location.ini"
    if location.is_file():
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetPrivateProfileStringW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD, wintypes.LPCWSTR]
        buffer = ctypes.create_unicode_buffer(32768)
        length = kernel.GetPrivateProfileStringW("Mavis", "DataHome", "", buffer, len(buffer), str(location))
        value = Path(buffer.value)
        if not length or length >= len(buffer)-1 or not value.is_absolute():
            raise ValueError("INVALID_INSTALLED_DATA_HOME")
        return value
    return None


def helper_main() -> int:
    """Console subsystem preserves private stdio; the UI executable stays windowed."""
    if "--residency" in sys.argv[1:]:
        sys.argv.remove("--residency")
        from scripts.mavis_performance import main
        return main()
    if "--voice-acceptance" in sys.argv[1:]:
        sys.argv.remove("--voice-acceptance")
        from scripts.mavis_voice_acceptance import main
        return main()
    if "--stop-stress" in sys.argv[1:]:
        sys.argv.remove("--stop-stress")
        from scripts.mavis_stop_stress import main
        return main()
    parser = argparse.ArgumentParser(description="Mavis fixed worker and installed diagnostics")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--worker", choices=tuple(WORKERS.values()))
    group.add_argument("--probe", choices=("runtime", "vault", "vault-read", "voice", "provider", "uia"))
    group.add_argument("--benchmark", action="store_true")
    group.add_argument("--backup-data", action="store_true")
    group.add_argument("--security-suite", action="store_true")
    parser.add_argument("--test-mode", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--data-home", type=Path)
    parser.add_argument("--models", type=Path)
    parser.add_argument("--ref")
    parser.add_argument("--target")
    parser.add_argument("--fixture-url")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=600)
    args = parser.parse_args()
    if args.test_mode and not args.worker:
        parser.error("--test-mode is only valid for the fixed private worker")
    if args.worker:
        module = next(module for module, name in WORKERS.items() if name == args.worker)
        sys.argv = [sys.argv[0], *(["--test-mode"] if args.test_mode else [])]
        return importlib.import_module(module).main()
    if args.security_suite:
        from .installed_security import run
        if args.output is None:
            parser.error("--security-suite requires a new --output report")
        report = run(args.output)
    elif args.backup_data:
        from .upgrade import backup_data
        if args.data_home is None:
            parser.error("--backup-data requires --data-home")
        report = backup_data(args.data_home / "DaFeiYuMavis")
    elif args.benchmark:
        from .release_benchmark import run
        if args.output is None or args.data_home is None:
            parser.error("--benchmark requires isolated --output and --data-home")
        return run(args)
    else:
        from .bundle_probe import run
        report = run(args)
    import json
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as file:
            json.dump(report, file, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report.get("passed", False) else 1
