"""Whitelisted diagnostics; no transcripts, screenshots, audio or vault contents."""
import importlib.metadata
import platform
from pathlib import Path
import zipfile
import json
import re

from .history import export_redact


def preview(store, settings, *, provider_checks, credential_state, last_error, runtime):
    from . import __version__
    versions = {}
    for name in ("PySide6", "sherpa-onnx", "keyring", "pydantic", "aiohttp"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not installed"
    from .contracts import utc_now
    last_error = last_error or next((task.error_code for task in store.tasks(limit=20) if task.error_code), None)
    if last_error and not re.fullmatch(r"[A-Z][A-Z0-9_]{1,100}", last_error):
        last_error = "LOCAL_ERROR_DETAILS_OMITTED"
    return export_redact({"application": "DaFeiYu Mavis", "version": __version__, "generated_at": utc_now().isoformat(),
        "upstream_commit": "34d810b1eadd98d00e7cb9b3b51428a45b5bf03e",
        "system": {"os": platform.system(), "release": platform.release(), "architecture": platform.machine(), "python": platform.python_version()},
        "dependencies": versions, "records": store.counts(), "provider": settings.provider.model_dump(),
        "provider_checks": dict(provider_checks), "credential": credential_state, "last_error": last_error, "runtime": runtime,
        "privacy": {"raw_audio_included": False, "screenshots_included": False, "task_text_included": False, "automatic_upload": False}})


def write_package(path: Path, content: dict):
    # The exact preview is exported. No directory walk or attachment discovery.
    with path.open("xb") as file, zipfile.ZipFile(file, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("diagnostics.json", json.dumps(export_redact(content), ensure_ascii=False, indent=2))


def clear_managed_reports(data_dir: Path):
    """Only this app's named backup/diagnostic cache, never arbitrary exports."""
    for folder in (data_dir / "diagnostics", data_dir / "backups"):
        if not folder.is_dir() or folder.is_symlink():
            continue
        for path in folder.iterdir():
            if path.is_file() and not path.is_symlink() and path.name.startswith("mavis-") and path.suffix in {".zip", ".json", ".bak"}:
                path.unlink()
    for name in ("state.db.pre-v1.bak", "state-test.db.pre-v1.bak"):
        path = data_dir / name
        if path.is_file() and not path.is_symlink():
            path.unlink()
