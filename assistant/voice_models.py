"""Pinned local speech resources; only manifest-listed model data is imported."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import urllib.request
from uuid import uuid4

MANIFEST = json.loads((Path(__file__).with_name("assets") / "voice-models.json").read_text(encoding="utf-8"))


def matches(path: Path, spec: dict) -> bool:
    if not path.is_file() or path.is_symlink() or path.stat().st_size != spec["bytes"]:
        return False
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest() == spec["sha256"]


class ModelManager:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def directory(self, kind: str) -> Path:
        return self.root / MANIFEST["models"][kind]["id"]

    def status(self) -> dict:
        result = {}
        for kind, spec in MANIFEST["models"].items():
            directory = self.directory(kind)
            result[kind] = "ready" if all(matches(directory / name, item) for name, item in spec["files"].items()) else "missing_or_invalid"
        return result

    def verify(self) -> None:
        if any(value != "ready" for value in self.status().values()):
            raise ValueError("VOICE_MODELS_MISSING_OR_INVALID")

    def prepare(self, import_dir: Path | None = None, progress=lambda message: None):
        """Download or import fixed data. Existing corrupt files are preserved for review."""
        self.root.mkdir(parents=True, exist_ok=True)
        for kind, spec in MANIFEST["models"].items():
            target = self.directory(kind)
            if target.is_symlink():
                raise ValueError("MODEL_DIRECTORY_SYMLINK")
            target.mkdir(exist_ok=True)
            missing = {name: item for name, item in spec["files"].items() if not matches(target / name, item)}
            if not missing:
                continue
            if any((target / name).exists() for name in missing):
                raise ValueError("MODEL_CORRUPT_DELETE_MANAGED_COPY_FIRST")
            progress(kind + ": preparing")
            if import_dir:
                candidates = [Path(import_dir) / spec["id"], Path(import_dir)]
                source = next((p for p in candidates if all(matches(p / n, i) for n, i in missing.items())), None)
                if source is None:
                    raise ValueError("IMPORT_HASH_MISMATCH_" + kind.upper())
                for name in missing:
                    with (source / name).open("rb") as src, (target / name).open("xb") as dst:
                        shutil.copyfileobj(src, dst)
                continue
            archive = self.root / ("download-" + uuid4().hex + (".tar.bz2" if "archive_root" in spec else ".onnx"))
            try:
                with urllib.request.urlopen(spec["url"], timeout=30) as response, archive.open("xb") as file:
                    received = 0
                    while block := response.read(1024 * 1024):
                        received += len(block)
                        if received > spec["bytes"]:
                            raise ValueError("MODEL_SIZE_MISMATCH")
                        file.write(block)
                if not matches(archive, spec):
                    raise ValueError("MODEL_ARCHIVE_HASH_MISMATCH")
                if "archive_root" in spec:
                    with tarfile.open(archive, "r:bz2") as tar:
                        for name in missing:
                            member = tar.getmember(spec["archive_root"] + "/" + name)
                            if not member.isfile():
                                raise ValueError("MODEL_MEMBER_NOT_REGULAR")
                            with tar.extractfile(member) as src, (target / name).open("xb") as dst:
                                shutil.copyfileobj(src, dst)
                else:
                    with archive.open("rb") as src, (target / "silero_vad.onnx").open("xb") as dst:
                        shutil.copyfileobj(src, dst)
            finally:
                if archive.is_file():
                    archive.unlink()  # our unique temporary download only
        self.verify()
        progress("ready")

    def delete(self):
        """Remove only our manifest-listed cache files; preserve unrelated user files."""
        for kind, spec in MANIFEST["models"].items():
            directory = self.directory(kind)
            if directory.is_symlink():
                raise ValueError("MODEL_DIRECTORY_SYMLINK")
            for name in spec["files"]:
                path = directory / name
                if path.is_file() and not path.is_symlink():
                    path.unlink()
