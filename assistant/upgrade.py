"""Read-only SQLite backups and bounded config snapshots before data migration."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
from uuid import uuid4


def backup_data(directory: Path) -> dict:
    """Preserve existing app data to a new folder; never copy credentials or media."""
    databases = [p for p in (directory / "state.db", directory / "state-test.db") if p.is_file() and not p.is_symlink()]
    configs = [p for p in directory.glob("*.json") if not p.is_symlink() and p.is_file() and p.stat().st_size <= 4 * 1024**2]
    if not databases and not configs:
        return {"passed": True, "status": "no_existing_data", "files": []}
    from . import __version__
    folder = directory / "backups" / ("pre-" + __version__ + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    folder.mkdir(parents=True)
    copied = []
    try:
        for path in databases:
            with sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True) as source, sqlite3.connect(folder / path.name) as target:
                source.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("BACKUP_DATABASE_INTEGRITY_FAILED")
            copied.append(path.name)
        for path in configs:
            shutil.copyfile(path, folder / path.name)
            copied.append(path.name)
        report = {"passed": True, "status": "backed_up", "directory": str(folder), "files": copied, "credentials_included": False}
    except (OSError, sqlite3.Error, RuntimeError) as error:
        report = {"passed": False, "status": "backup_failed", "code": type(error).__name__, "directory": str(folder), "files": copied}
    (folder / "backup.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
