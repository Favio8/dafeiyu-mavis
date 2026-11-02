"""Prepare the Mavis speech cache with pinned downloads or offline model data."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--import-dir", type=Path)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from assistant.voice_models import ModelManager
    manager = ModelManager(args.root)
    if args.import_dir or args.download:
        manager.prepare(args.import_dir, progress=print)
    print(json.dumps(manager.status()))
    return 0 if all(v == "ready" for v in manager.status().values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
