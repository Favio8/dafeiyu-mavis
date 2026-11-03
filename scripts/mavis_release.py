"""Pinned Mavis onedir + per-user installer + portable archive build recipe."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
VERSION = "0.1.0"


def sha(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def execute(command: list[str], log: Path, *, env=None) -> None:
    """Keep exact commands, output and failures; never run through a shell."""
    started = time.monotonic()
    with log.open("x", encoding="utf-8") as file:
        file.write("COMMAND="+json.dumps(command)+"\n")
        file.flush()
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=file, stderr=subprocess.STDOUT)
        file.write(f"\nEXIT_CODE={result.returncode}\nELAPSED_S={time.monotonic()-started:.3f}\n")
    if result.returncode:
        raise RuntimeError("BUILD_COMMAND_FAILED: "+log.name)


def licenses(stage: Path) -> list[dict]:
    """Copy installed license texts as notices; metadata is not a grant of rights."""
    output = stage / "licenses"
    output.mkdir()
    shutil.copytree(ROOT / "packaging/licenses", output / "ffmpeg")
    import imageio_ffmpeg
    for flag, name in (("-L", "binary-license.txt"), ("-buildconf", "binary-buildconf.txt")):
        result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), flag], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
        (output / "ffmpeg" / name).write_bytes(result.stdout)
    inventory = []
    for dist in sorted(importlib.metadata.distributions(), key=lambda d: d.metadata.get("Name", "").lower()):
        name = dist.metadata.get("Name", "unknown")
        files = []
        for entry in dist.files or []:
            if not any(word in str(entry).lower() for word in ("license", "copying", "notice")):
                continue
            source = Path(dist.locate_file(entry))
            if not source.is_file() or source.stat().st_size > 2*1024**2:
                continue
            destination = output / name / entry.name
            destination.parent.mkdir(exist_ok=True)
            if destination.exists():
                destination = destination.with_name(sha(source)[:8]+"-"+destination.name)
            shutil.copyfile(source, destination)
            files.append({"name": str(destination.relative_to(stage)), "sha256": sha(destination)})
        inventory.append({"name": name, "version": dist.version, "license": dist.metadata.get("License-Expression") or dist.metadata.get("License") or "not declared", "notices": files})
    (output / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    return inventory


def verify_bundle(folder: Path, logs: Path) -> dict:
    required = [folder / "DaFeiYuMavis.exe", folder / "mavis-worker.exe",
                folder / "_internal/LICENSE", folder / "_internal/THIRD_PARTY_NOTICES.md",
                folder / "_internal/assistant/assets/voice-models.json", folder / "_internal/assistant/assets/mavis.svg",
                folder / "_internal/PySide6/plugins/platforms/qwindows.dll"]
    missing = [str(p.relative_to(folder)) for p in required if not p.is_file()]
    if missing:
        raise RuntimeError("MISSING_BUNDLE_FILES: "+", ".join(missing))
    execute([sys.executable, "scripts/check_frameseq_bundle.py", "--characters-dir", str(folder / "_internal/assets/characters")], logs / "material-bundle.txt")
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(folder / "mavis-worker.exe"))
    pyz_name = next(n for n in archive.toc if n.endswith(".pyz"))
    modules = archive.open_embedded_archive(pyz_name).toc
    expected = ["assistant.native_worker", "assistant.voice_worker", "assistant.model_probe_worker", "assistant.release_benchmark", "keyring.backends.Windows", "win32ctypes.pywin32.win32cred", "comtypes.gen.UIAutomationClient"]
    missing_modules = [m for m in expected if m not in modules]
    if missing_modules:
        raise RuntimeError("MISSING_FROZEN_MODULES: "+", ".join(missing_modules))
    built_in_audio = {}
    for name in ("click.wav", "agent/start.wav", "agent/done.wav", "agent/error.wav"):
        source_name = "assets/sounds/"+name
        original = subprocess.check_output(["git", "show", "34d810b1eadd98d00e7cb9b3b51428a45b5bf03e:"+source_name], cwd=ROOT)
        built_in_audio["_internal/"+source_name] = hashlib.sha256(original).hexdigest()
    private = []
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(folder).as_posix()
        if path.suffix.lower() == ".wav" and (relative not in built_in_audio or sha(path) != built_in_audio[relative]):
            private.append(path)
        elif path.suffix.lower() == ".db" or path.name in {"assistant-settings.json", "voice-preferences.json", ".env"}:
            private.append(path)
    if private:
        raise RuntimeError("PRIVATE_DATA_IN_BUNDLE")
    from scripts.check_bundle_encoding import check_bundle
    chinese = next((p.name for p in (folder / "_internal/assets/characters").rglob("*") if p.is_file() and any(ord(c) > 127 for c in p.name)), None)
    if chinese is None:
        raise RuntimeError("MISSING_CHINESE_ASSET_FILENAME")
    encoding_errors = check_bundle(folder, code_literals=("任务记录", "控制中心", "记事本"), filename_needles=(chinese,))
    (logs / "encoding.json").write_text(json.dumps({"errors": encoding_errors, "variant": "mavis", "legacy_chat_literals_not_applicable": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    if encoding_errors:
        raise RuntimeError("BUNDLE_ENCODING_FAILED")
    report = {"passed": True, "required_files": [str(p.relative_to(folder)) for p in required], "required_modules": expected,
              "input_lock_sha256": sha(ROOT / "requirements-mavis.lock.txt"), "speech_weights_bundled": False,
              "built_in_synthesized_audio_matches_fixed_upstream": built_in_audio,
              "files": [{"name": str(p.relative_to(folder)).replace("\\", "/"), "size": p.stat().st_size, "sha256": sha(p)} for p in sorted(folder.rglob("*")) if p.is_file()]}
    (logs / "bundle-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def portable(folder: Path, destination: Path, epoch: int) -> None:
    date = datetime.fromtimestamp(max(epoch, 315532800), timezone.utc)
    stamp = (date.year, date.month, date.day, date.hour, date.minute, date.second//2*2)
    with zipfile.ZipFile(destination, "x") as archive:
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            info = zipfile.ZipInfo("DaFeiYuMavis/"+path.relative_to(folder).as_posix(), stamp)
            info.compress_type = zipfile.ZIP_STORED if path.suffix.lower() in {".webp", ".webm", ".png", ".zip"} else zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            with path.open("rb") as source, archive.open(info, "w") as target:
                shutil.copyfileobj(source, target, 1024**2)


def build(args) -> None:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    epoch = int(subprocess.check_output(["git", "show", "-s", "--format=%ct", "HEAD"], cwd=ROOT, text=True))
    identifier = commit[:8]+"-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = (args.output or ROOT / "dist-mavis" / VERSION / identifier).resolve()
    candidate.mkdir(parents=True)
    logs = candidate / "evidence"
    logs.mkdir()
    stage = ROOT / ".scratch/m6/build" / identifier
    stage.mkdir(parents=True)
    env = os.environ.copy()
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONHASHSEED="0", SOURCE_DATE_EPOCH=str(epoch), MAVIS_BUILD_STAGE=str(stage), ANONYMIZED_TELEMETRY="false")
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    execute([sys.executable, "scripts/prepare_frameseq_bundle.py"], logs / "material-source.txt", env=env)
    if importlib.metadata.version("PyInstaller") != "6.16.0":
        raise RuntimeError("PYINSTALLER_VERSION_MISMATCH")
    if sys.version_info[:3] != (3, 11, 14):
        raise RuntimeError("PYTHON_VERSION_MISMATCH")
    info = {"version": VERSION, "source_commit": commit, "upstream_commit": "34d810b1eadd98d00e7cb9b3b51428a45b5bf03e", "python": sys.version.split()[0],
            "requirements_sha256": sha(ROOT / "requirements-mavis.lock.txt"), "source_date_epoch": epoch,
            "build_type": "onedir x64; UI windowed plus fixed console helper", "release_gate": "not_passed",
            "models": "pinned external download/local import; no weights bundled", "reproducibility": "pinned recipe; independent byte-identical rebuild not yet verified"}
    (stage / "build-info.json").write_text(json.dumps(info, sort_keys=True, indent=2), encoding="utf-8")
    (stage / "version.txt").write_text('''VSVersionInfo(ffi=FixedFileInfo(filevers=(0,1,0,0),prodvers=(0,1,0,0),mask=0x3f,flags=0,OS=0x40004,fileType=1,subtype=0,date=(0,0)),kids=[StringFileInfo([StringTable('040904B0',[StringStruct('CompanyName','Favio8'),StringStruct('FileDescription','DaFeiYu Mavis'),StringStruct('FileVersion','0.1.0'),StringStruct('ProductName','DaFeiYu Mavis'),StringStruct('ProductVersion','0.1.0')])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])''', encoding="utf-8")
    shutil.copyfile(ROOT / "assistant/assets/mavis.ico", stage / "icon.ico")
    licenses(stage)
    execute([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(candidate / "onedir"), "--workpath", str(stage / "pyinstaller"), "packaging/mavis.spec"], logs / "pyinstaller.txt", env=env)
    folder = candidate / "onedir/DaFeiYuMavis"
    (folder / "portable.json").write_text(json.dumps({"schema": 1, "data": "data", "version": VERSION}), encoding="utf-8")
    finish_package(folder, candidate, logs, args, info, env)


def finish_package(folder: Path, candidate: Path, logs: Path, args, info: dict, env=None) -> None:
    """Reuse an unchanged onedir after a packaging-only fix; preserve the old source SHA."""
    verify_bundle(folder, logs)
    compiler = args.iscc or ROOT / ".scratch/m6/tools/InnoSetup6.7.4/ISCC.exe"
    if not compiler.is_file():
        raise FileNotFoundError("INNO_SETUP_6_7_4_COMPILER_REQUIRED")
    toolchain = json.loads((ROOT / "packaging/windows-toolchain.json").read_text(encoding="utf-8"))["inno_setup"]
    for name, expected_hash in toolchain["files"].items():
        if not (compiler.parent / name).is_file() or sha(compiler.parent / name) != expected_hash:
            raise RuntimeError("INNO_SETUP_COMPONENT_HASH_MISMATCH: "+name)
    info["installer_compiler"] = toolchain
    execute([str(compiler), "/Qp", "/DMyAppDir="+str(folder), "/DMyOutputDir="+str(candidate), "packaging/mavis.iss"], logs / "inno.txt", env=env)
    if not args.no_zip:
        portable(folder, candidate / f"DaFeiYu-Mavis-{VERSION}-win-x64-portable.zip", info["source_date_epoch"])
    info["packaging_source_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    info["spec_sha256"] = sha(ROOT / "packaging/mavis.spec")
    info["artifacts"] = [{"name": p.name, "bytes": p.stat().st_size, "sha256": sha(p)} for p in sorted(candidate.iterdir()) if p.is_file()]
    (candidate / "BUILD_MANIFEST.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    checksums(candidate)
    print(json.dumps({"candidate": str(candidate), "artifacts": info["artifacts"], "release_gate": "not_passed"}))


def checksums(folder: Path) -> None:
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt")
    (folder / "SHA256SUMS.txt").write_text("\n".join(sha(p)+"  "+p.name for p in files)+"\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "package", "verify", "checksums"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--app-dir", type=Path)
    parser.add_argument("--iscc", type=Path)
    parser.add_argument("--no-zip", action="store_true")
    args = parser.parse_args()
    if args.command == "build":
        build(args)
    elif args.command == "package":
        if args.app_dir is None or args.output is None:
            parser.error("package requires --app-dir and its candidate --output")
        if (args.output / "BUILD_MANIFEST.json").exists():
            parser.error("refusing to replace a completed delivery candidate")
        logs = args.output / "evidence" / ("package-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        logs.mkdir(parents=True)
        info = json.loads((args.app_dir / "_internal/build-info.json").read_text(encoding="utf-8"))
        finish_package(args.app_dir.resolve(), args.output.resolve(), logs, args, info)
    elif args.command == "verify":
        if args.app_dir is None or args.output is None:
            parser.error("verify requires --app-dir and --output evidence folder")
        args.output.mkdir(parents=True)
        verify_bundle(args.app_dir, args.output)
    else:
        if args.output is None:
            parser.error("checksums requires --output")
        checksums(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
