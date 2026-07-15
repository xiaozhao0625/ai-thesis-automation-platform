from __future__ import annotations

import hashlib
import json
from pathlib import Path


PLATFORM_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PLATFORM_ROOT / "benchmark" / "ingest-fixture-v1"
MANIFEST_PATH = PLATFORM_ROOT / "benchmark" / "fixture-manifest.json"


def main() -> int:
    files = sorted(path for path in FIXTURE_ROOT.rglob("*") if path.is_file())
    if len(files) != 128:
        raise RuntimeError(f"expected 128 fixture files, found {len(files)}")
    manifest = {
        "fixture_version": "ingest-fixture-v1",
        "source": "ingest-cli/tests/fixtures/build_controlled_sample.py",
        "license": "CC0-1.0 synthetic test data",
        "file_count": len(files),
        "sha256": {
            path.relative_to(FIXTURE_ROOT).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in files
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {MANIFEST_PATH} with {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
