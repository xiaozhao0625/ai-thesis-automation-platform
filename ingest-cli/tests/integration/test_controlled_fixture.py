from __future__ import annotations

from pathlib import Path

from thesis_ingest.pipeline import run_scan
from thesis_ingest.verification import verify_package
from tests.fixtures.build_controlled_sample import (
    FIXTURE_FILE_COUNT,
    FIXTURE_LICENSE,
    build_controlled_sample,
    fixture_files,
)
from tests.support import write_config


def test_fixture_is_exactly_128_synthetic_redistributable_files() -> None:
    files = fixture_files()

    assert len(files) == FIXTURE_FILE_COUNT == 128
    assert FIXTURE_LICENSE.startswith("CC0-1.0")
    assert all(path.startswith("project/") for path in files)


def test_fixture_generation_is_byte_for_byte_deterministic(tmp_path: Path) -> None:
    first = build_controlled_sample(tmp_path / "first")
    second = build_controlled_sample(tmp_path / "second")

    assert first == second
    assert len(first) == 128


def test_executable_placeholders_have_no_executable_payload() -> None:
    files = fixture_files()
    executable_placeholders = {
        path: payload
        for path, payload in files.items()
        if Path(path).suffix.casefold() in {".exe", ".dll"}
    }

    assert executable_placeholders
    assert all(payload.startswith(b"MZ SYNTHETIC INERT") for payload in executable_placeholders.values())
    assert all(b"NOT EXECUTABLE" in payload for payload in executable_placeholders.values())


def test_full_128_file_fixture_scans_and_verifies(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    build_controlled_sample(source)
    config = write_config(
        tmp_path / "ingest-config.json",
        source_root=source,
        output_directory="ingest-output/",
        checkpoint_every_records=16,
    )

    result = run_scan(config, scan_id="scan-controlled-128")
    report = verify_package(result.output_path)

    assert result.status == "COMPLETED"
    assert report.status == "COMPLETED"
    assert (
        report.record_counts["artifacts.jsonl"]
        + report.record_counts["excluded-items.jsonl"]
        == 128
    )
