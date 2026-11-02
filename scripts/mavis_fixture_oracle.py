"""Independent, read-only oracle for a new UTF-8 test document."""
import argparse
import hashlib
import json
from pathlib import Path


def check(path: Path, expected_sha256: str) -> dict:
    """Read an existing fixture result, never create or alter it for the executor."""
    if not path.is_file():
        return {"result": "failed", "reason": "file_absent"}
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"result": "passed" if actual == expected_sha256 else "failed", "sha256": actual}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("expected_sha256")
    args = parser.parse_args()
    result = check(args.file, args.expected_sha256)
    print(json.dumps(result))
    raise SystemExit(0 if result["result"] == "passed" else 1)
