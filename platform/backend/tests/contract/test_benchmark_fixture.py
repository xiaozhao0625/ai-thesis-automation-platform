from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_ROOT = REPOSITORY_ROOT / "platform" / "benchmark" / "ingest-fixture-v1"
MANIFEST_PATH = REPOSITORY_ROOT / "platform" / "benchmark" / "fixture-manifest.json"


def test_benchmark_fixture_has_exact_frozen_inventory_and_hashes() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text("utf-8"))
    files = sorted(path for path in FIXTURE_ROOT.rglob("*") if path.is_file())

    assert manifest["fixture_version"] == "ingest-fixture-v1"
    assert manifest["file_count"] == len(files) == 128
    assert manifest["license"] == "CC0-1.0 synthetic test data"
    expected = {
        path.relative_to(FIXTURE_ROOT).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in files
    }
    assert manifest["sha256"] == expected


def test_benchmark_contains_no_reference_to_historical_library_root() -> None:
    forbidden = ("15万", "历史论文库", "D:/2026毕设", "D:\\2026毕设")

    for path in FIXTURE_ROOT.rglob("*"):
        if path.is_file():
            text = path.read_bytes().decode("utf-8", errors="ignore")
            assert not any(item in text for item in forbidden), path
