from __future__ import annotations

import json
from pathlib import Path


def build_small_source(root: Path) -> dict[str, bytes]:
    files = {
        "project/任务书.docx": b"synthetic requirement document",
        "project/论文终稿.docx": b"synthetic thesis final document " * 40,
        "project/src/a.py": b"print('same')\n",
        "project/src/b.py": b"print('b')\n",
        "project/src/c.py": b"print('c')\n",
        "project/copy/a.py": b"print('same')\n",
        "project/requirements.txt": b"pytest==9.0.3\n",
        "project/pyproject.toml": b"[project]\nname='fixture'\n",
        "project/README.md": b"# Synthetic project\n",
        "project/tests/test_a.py": b"def test_a(): assert True\n",
        "project/migrations/001_create.sql": b"CREATE TABLE sample(id int);\n",
        "project/.venv/Lib/site.py": b"third party venv content\n",
        "project/vendor/pkg/data.pdf": b"%PDF-safe synthetic dependency\n",
        "project/tools/run.exe": b"MZ\x00\x00safe inert fixture\n",
        "project/config/secrets.json": b'{"token":"synthetic-not-real"}\n',
        "project/参考文献线索.txt": (
            "Smith J. Useful Title. 2024. doi:10.1234/example\n"
        ).encode("utf-8"),
        "project/screenshots/student-face.jpg": b"safe synthetic image placeholder\n",
    }
    for relative_path, payload in files.items():
        destination = root / Path(*relative_path.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    return files


def write_config(
    path: Path,
    *,
    source_root: Path,
    output_directory: str,
    checkpoint_every_records: int = 1,
) -> Path:
    config = {
        "config_version": "0.1",
        "source_mount": {
            "schema_version": "0.1",
            "record_type": "SOURCE_MOUNT",
            "source_mount_id": "controlled-sample",
            "name": "Controlled sample",
            "mount_type": "LOCAL_DIRECTORY",
            "root_uri": source_root.resolve().as_uri(),
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
            "output_directory": output_directory,
            "jsonl_flush_records": 4,
            "checkpoint_every_records": checkpoint_every_records,
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
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return path


def read_jsonl(path: Path) -> list[dict[str, object]]:
    payload = path.read_bytes()
    if not payload:
        return []
    return [
        json.loads(line)
        for line in payload.decode("utf-8").splitlines()
        if line
    ]
