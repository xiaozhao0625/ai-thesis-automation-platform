from __future__ import annotations

import hashlib
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = PROJECT_ROOT / "contracts" / "v0.1"
EXPECTED_HASHES = {
    "source-mount.schema.json": (
        "a5c92d3f3406e41c9c7b82d722e55d7892995c687939d7b92d6111788ce03f01"
    ),
    "ingest-manifest.schema.json": (
        "3aa06774def320ab91cc3a0f6daed69030c83600267f41262943256cee806cc9"
    ),
    "artifact-ingest-record.schema.json": (
        "8bd19a3d5dc9c38ccc7fd75e4242b19f161ae6bf5138403df0884ea6f003a62d"
    ),
    "engineering-result.schema.json": (
        "4ccf1837514c7df1be083f7791840874c1345114a568f30dd19ecf837b673d5e"
    ),
}


def test_contract_directory_contains_exactly_the_frozen_schema_snapshot() -> None:
    schema_names = {
        path.name for path in CONTRACT_ROOT.glob("*.schema.json") if path.is_file()
    }

    assert schema_names == set(EXPECTED_HASHES)
    for name, expected_hash in EXPECTED_HASHES.items():
        actual_hash = hashlib.sha256((CONTRACT_ROOT / name).read_bytes()).hexdigest()
        assert actual_hash == expected_hash


def test_contract_lock_matches_every_frozen_schema() -> None:
    lock = json.loads((CONTRACT_ROOT / "contract-lock.json").read_text("utf-8"))

    assert lock["contract_version"] == "0.1"
    assert lock["hash_algorithm"] == "sha256"
    assert lock["schemas"] == EXPECTED_HASHES
