from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.support import build_small_source, write_config
from thesis_ingest.pipeline import ScanInterrupted, run_scan


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def command(cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "thesis_ingest", *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_scan_and_verify_commands_complete_from_a_fresh_directory(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    build_small_source(source)
    config = write_config(
        tmp_path / "ingest-config.json",
        source_root=source,
        output_directory="ingest-output/",
    )

    scan = command(
        tmp_path,
        "scan",
        "--config",
        str(config),
        "--output",
        "ingest-output/",
    )
    verify = command(
        tmp_path,
        "verify",
        "--manifest",
        str(tmp_path / "ingest-output" / "ingest-manifest.json"),
    )

    assert scan.returncode == 0, scan.stderr
    assert '"status": "COMPLETED"' in scan.stdout
    assert verify.returncode == 0, verify.stderr
    assert '"verified": true' in verify.stdout


def test_config_or_cli_output_mismatch_returns_exit_code_two(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    config = write_config(
        tmp_path / "ingest-config.json",
        source_root=source,
        output_directory="expected/",
    )

    completed = command(
        tmp_path,
        "scan",
        "--config",
        str(config),
        "--output",
        "different/",
    )

    assert completed.returncode == 2
    assert "CLI_OUTPUT_MISMATCH" in completed.stderr


def test_missing_source_mount_returns_exit_code_three(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    config_path = write_config(
        tmp_path / "ingest-config.json",
        source_root=source,
        output_directory="ingest-output/",
    )
    config = json.loads(config_path.read_text("utf-8"))
    config["source_mount"]["root_uri"] = (tmp_path / "missing").resolve().as_uri()
    config_path.write_text(json.dumps(config), encoding="utf-8")

    completed = command(
        tmp_path,
        "scan",
        "--config",
        str(config_path),
        "--output",
        "ingest-output/",
    )

    assert completed.returncode == 3
    assert "SOURCE_ROOT_NOT_FOUND" in completed.stderr


def test_tampered_package_verify_returns_exit_code_five(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    build_small_source(source)
    config = write_config(
        tmp_path / "ingest-config.json",
        source_root=source,
        output_directory="ingest-output/",
    )
    scan = command(
        tmp_path,
        "scan",
        "--config",
        str(config),
        "--output",
        "ingest-output/",
    )
    assert scan.returncode == 0, scan.stderr
    (tmp_path / "ingest-output" / "summary.json").write_bytes(b"{}\n")

    completed = command(
        tmp_path,
        "verify",
        "--manifest",
        str(tmp_path / "ingest-output" / "ingest-manifest.json"),
    )

    assert completed.returncode == 5
    assert "OUTPUT_HASH_MISMATCH" in completed.stderr


@pytest.mark.recovery
def test_standard_scan_command_auto_resumes_matching_checkpoint(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    build_small_source(source)
    config = write_config(
        tmp_path / "ingest-config.json",
        source_root=source,
        output_directory="ingest-output/",
    )
    try:
        run_scan(config, scan_id="scan-cli-resume", fail_after_records=4)
    except ScanInterrupted:
        pass
    else:
        raise AssertionError("fault injection did not interrupt the scan")

    completed = command(
        tmp_path,
        "scan",
        "--config",
        str(config),
        "--output",
        "ingest-output/",
    )

    assert completed.returncode == 0, completed.stderr
    assert '"resumed_from_checkpoint": true' in completed.stdout
