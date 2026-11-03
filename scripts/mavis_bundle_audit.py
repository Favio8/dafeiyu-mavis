"""Scan actual distribution bytes and embedded code without exporting credential values."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from assistant.credentials import Credentials
    secret = Credentials().read("deepseek/default")
    needles = [secret.encode(), secret.encode("utf-16-le"), base64.b64encode(secret.encode())] if secret else []
    personal = []
    for value in (str(ROOT), os.environ.get("USERPROFILE", "")):
        if value:
            for text in (value, value.replace("\\", "/")):
                personal.extend([text.encode(), text.encode("utf-16-le")])
    hits, paths = [], []
    count = total = 0
    overlap = max([len(n) for n in needles+personal] or [1])-1
    for path in args.app_dir.rglob("*"):
        if not path.is_file():
            continue
        count += 1
        total += path.stat().st_size
        found_key = found_personal = False
        tail = b""
        with path.open("rb") as file:
            while chunk := file.read(1024**2):
                data = tail+chunk
                found_key |= any(n in data for n in needles)
                found_personal |= any(n in data for n in personal)
                tail = data[-overlap:] if overlap else b""
        if found_key:
            hits.append(path.relative_to(args.app_dir).as_posix())
        if found_personal:
            paths.append(path.relative_to(args.app_dir).as_posix())
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(args.app_dir / "mavis-worker.exe"))
    pyz = archive.open_embedded_archive(next(name for name in archive.toc if name.endswith(".pyz")))
    embedded = 0
    for name in pyz.toc:
        code = pyz.extract(name)
        stack = [code]
        while stack:
            item = stack.pop()
            if isinstance(item, types.CodeType):
                embedded += 1
                stack.extend(item.co_consts)
                stack.append(item.co_filename)
            elif isinstance(item, (tuple, list)):
                stack.extend(item)
            elif isinstance(item, (str, bytes)):
                data = item.encode("utf-8", errors="surrogatepass") if isinstance(item, str) else item
                if any(n in data for n in needles):
                    hits.append("PYZ:"+name)
                if any(n in data for n in personal):
                    paths.append("PYZ:"+name)
    report = {"passed": not hits and not paths, "files": count, "bytes": total, "embedded_code_objects": embedded,
              "credential_present_for_in_memory_comparison": bool(secret), "credential_matches": sorted(set(hits)),
              "personal_build_path_matches": sorted(set(paths)), "raw_credential_exported": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(report, file, indent=2)
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
