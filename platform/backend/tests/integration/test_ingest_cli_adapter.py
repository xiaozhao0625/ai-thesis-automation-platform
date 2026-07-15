from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.ingest_adapter.adapter import IngestCliAdapter


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.integration
def test_adapter_runs_existing_scan_and_verify_without_copying_cli_rules(
    tmp_path: Path,
) -> None:
    source = tmp_path / "controlled-source"
    files = {
        "project/任务书.docx": b"synthetic requirement",
        "project/src/main.py": b"print('synthetic')\n",
        "project/src/main-copy.py": b"print('synthetic')\n",
        "project/.venv/Lib/site.py": b"synthetic dependency",
        "project/quarantine/run.exe": b"MZ inert synthetic fixture",
        "project/references/参考文献线索.txt": (
            "Smith J. Synthetic Reference. 2024. doi:10.1234/synthetic\n"
        ).encode("utf-8"),
    }
    for relative, payload in files.items():
        path = source / Path(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    result = IngestCliAdapter(
        cli_src=REPOSITORY_ROOT / "ingest-cli" / "src",
        work_root=tmp_path / "attempt-work",
    ).scan_and_verify(
        source_root=source,
        task_id=uuid4(),
        node_run_id=uuid4(),
        attempt_id=uuid4(),
    )

    assert result.scan_exit_code == 0
    assert result.verify_exit_code == 0
    assert result.manifest["status"] == "COMPLETED"
    assert result.summary["total_files"] == len(files)
    assert {path.name for path in result.output_files} == {
        "artifacts.jsonl",
        "duplicate-groups.jsonl",
        "excluded-items.jsonl",
        "ingest-issues.jsonl",
        "ingest-manifest.json",
        "primary-candidates.jsonl",
        "reference-candidates.jsonl",
        "sensitive-items.jsonl",
        "source-mounts.json",
        "summary.json",
    }
    assert source.joinpath("project/src/main.py").read_bytes() == files[
        "project/src/main.py"
    ]
