from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from app.core.errors import ApplicationError


OUTPUT_NAMES = {
    "ingest-manifest.json",
    "source-mounts.json",
    "artifacts.jsonl",
    "excluded-items.jsonl",
    "duplicate-groups.jsonl",
    "primary-candidates.jsonl",
    "reference-candidates.jsonl",
    "sensitive-items.jsonl",
    "ingest-issues.jsonl",
    "summary.json",
}


class IngestAdapterError(ApplicationError):
    pass


@dataclass(frozen=True, slots=True)
class IngestRunResult:
    output_directory: Path
    output_files: tuple[Path, ...]
    manifest: dict[str, object]
    summary: dict[str, object]
    scan_exit_code: int
    verify_exit_code: int
    scan_stdout: str
    scan_stderr: str
    verify_stdout: str
    verify_stderr: str


class IngestCliAdapter:
    def __init__(
        self,
        *,
        cli_src: Path,
        work_root: Path,
        timeout_seconds: int = 600,
    ) -> None:
        self.cli_src = cli_src.resolve()
        self.work_root = work_root.resolve()
        self.timeout_seconds = timeout_seconds

    def scan_and_verify(
        self,
        *,
        source_root: Path,
        task_id: UUID,
        node_run_id: UUID,
        attempt_id: UUID,
    ) -> IngestRunResult:
        source_root = source_root.resolve(strict=True)
        attempt_root = self.work_root / str(attempt_id)
        attempt_root.mkdir(parents=True, exist_ok=False)
        config_path = attempt_root / "ingest-config.json"
        output_directory = attempt_root / "ingest-output"
        config_path.write_text(
            json.dumps(
                _build_config(source_root, task_id),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        environment = os.environ.copy()
        existing_pythonpath = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = os.pathsep.join(
            value
            for value in (str(self.cli_src), existing_pythonpath)
            if value
        )
        scan = self._run(
            [
                sys.executable,
                "-m",
                "thesis_ingest",
                "scan",
                "--config",
                str(config_path),
                "--output",
                "ingest-output/",
            ],
            cwd=attempt_root,
            environment=environment,
        )
        if scan.returncode != 0:
            raise IngestAdapterError(
                "INGEST_SCAN_FAILED",
                "Ingest CLI scan failed",
                details={
                    "exit_code": scan.returncode,
                    "stderr": scan.stderr[-4000:],
                },
            )
        manifest_path = output_directory / "ingest-manifest.json"
        verify = self._run(
            [
                sys.executable,
                "-m",
                "thesis_ingest",
                "verify",
                "--manifest",
                str(manifest_path),
            ],
            cwd=attempt_root,
            environment=environment,
        )
        if verify.returncode != 0:
            raise IngestAdapterError(
                "INGEST_VERIFY_FAILED",
                "Ingest CLI verify failed",
                details={
                    "exit_code": verify.returncode,
                    "stderr": verify.stderr[-4000:],
                },
            )
        files = tuple(sorted(output_directory.iterdir(), key=lambda path: path.name))
        if {path.name for path in files} != OUTPUT_NAMES:
            raise IngestAdapterError(
                "INGEST_OUTPUT_INCOMPLETE",
                "Ingest CLI output set does not match the frozen contract",
            )
        manifest = json.loads(manifest_path.read_text("utf-8"))
        summary = json.loads((output_directory / "summary.json").read_text("utf-8"))
        if manifest.get("status") != "COMPLETED":
            raise IngestAdapterError(
                "INGEST_MANIFEST_NOT_COMPLETED",
                "verified manifest is not COMPLETED",
            )
        return IngestRunResult(
            output_directory=output_directory,
            output_files=files,
            manifest=manifest,
            summary=summary,
            scan_exit_code=scan.returncode,
            verify_exit_code=verify.returncode,
            scan_stdout=scan.stdout,
            scan_stderr=scan.stderr,
            verify_stdout=verify.stdout,
            verify_stderr=verify.stderr,
        )

    def _run(
        self,
        command: list[str],
        *,
        cwd: Path,
        environment: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )


def _build_config(source_root: Path, task_id: UUID) -> dict[str, object]:
    source_mount_id = f"task-{task_id}"
    return {
        "config_version": "0.1",
        "source_mount": {
            "schema_version": "0.1",
            "record_type": "SOURCE_MOUNT",
            "source_mount_id": source_mount_id,
            "name": "P1-1 controlled task material",
            "mount_type": "LOCAL_DIRECTORY",
            "root_uri": source_root.as_uri(),
            "binding_revision": 1,
            "read_only": True,
            "status": "ACTIVE",
            "case_policy": "CASE_SENSITIVE",
            "unicode_normalization": "NFC",
            "path_normalization_version": "path-nfc-posix-v1",
            "last_scan_id": None,
            "last_scan_at": None,
            "root_fingerprint": None,
            "access_policy": {
                "preview_policy": "RESTRICTED",
                "external_model_policy": "DENY_EXTERNAL_MODEL",
                "export_policy": "REDACT_SOURCE_URI",
                "audit_required": True,
            },
        },
        "rule_set_version": "ingest-rules-0.1",
        "scanner_version": "thesis-ingest-0.1",
        "path_normalization_version": "path-nfc-posix-v1",
        "hash_algorithm": "SHA-256",
        "path_rules": {
            "exclude_directories": [
                ".git",
                ".idea",
                ".venv",
                ".vscode",
                "__pycache__",
                "build",
                "coverage",
                "dist",
                "node_modules",
                "target",
                "venv",
            ],
            "exclude_file_name_patterns": ["*.autosave", "*.log.*", "~$*"],
            "max_file_size_bytes": 2_147_483_648,
        },
        "quarantine_rules": {
            "extensions": [".bat", ".cmd", ".dll", ".exe", ".jar", ".ps1"],
            "quarantine_unknown_binary": True,
            "quarantine_database_dump": True,
            "detect_credential_risk": True,
            "inspect_archives": True,
        },
        "sensitive_classification": {
            "enabled": True,
            "content_categories": [
                "FACE_IMAGE",
                "PERSONAL_DATA",
                "QUESTIONNAIRE",
                "INTERVIEW",
                "DATABASE_DUMP",
                "CREDENTIAL",
                "SOURCE_CODE",
                "VIDEO",
                "AUDIO",
            ],
        },
        "output": {
            "output_directory": "ingest-output/",
            "jsonl_flush_records": 32,
            "checkpoint_every_records": 16,
            "emit_excluded_item_records": True,
            "encoding": "UTF-8",
            "line_ending": "LF",
        },
        "capability_pack": {
            "pack_id": "python_web_management_v1",
            "classification_rule_version": "artifact-classification-0.1",
        },
        "project_scopes": [
            {
                "scope_id": "project",
                "source": "CONFIG",
                "relative_path_prefix": "project",
            }
        ],
        "symlink_policy": "DO_NOT_FOLLOW",
        "consistency_policy": "BEST_EFFORT",
        "resume_policy": "CHECKPOINT_STRICT",
    }
