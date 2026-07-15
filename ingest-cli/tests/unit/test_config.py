from __future__ import annotations

import json
from pathlib import Path

import pytest

from thesis_ingest.config import ConfigError, load_config, load_rule_bundle


def valid_config(root: Path, output_directory: str = "ingest-output/") -> dict:
    return {
        "config_version": "0.1",
        "source_mount": {
            "schema_version": "0.1",
            "record_type": "SOURCE_MOUNT",
            "source_mount_id": "controlled-sample",
            "name": "Controlled sample",
            "mount_type": "LOCAL_DIRECTORY",
            "root_uri": root.resolve().as_uri(),
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
            "exclude_directories": [".git", ".venv", "node_modules"],
            "exclude_file_name_patterns": ["*.autosave", "~$*"],
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
            "jsonl_flush_records": 1000,
            "checkpoint_every_records": 5000,
            "emit_excluded_item_records": True,
            "encoding": "UTF-8",
            "line_ending": "LF",
        },
        "capability_pack": {
            "pack_id": "python_web_management_v1",
            "classification_rule_version": "artifact-classification-0.1",
        },
        "project_scopes": [],
        "symlink_policy": "DO_NOT_FOLLOW",
        "consistency_policy": "BEST_EFFORT",
        "resume_policy": "CHECKPOINT_STRICT",
    }


def write_config(path: Path, config: dict) -> None:
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")


def test_config_relative_output_is_resolved_from_config_directory(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    config_path = tmp_path / "settings" / "ingest-config.json"
    config_path.parent.mkdir()
    write_config(config_path, valid_config(source, "../results/"))

    loaded = load_config(config_path)

    assert loaded.root_path == source.resolve()
    assert loaded.output_path == (tmp_path / "results").resolve()


def test_cli_output_is_resolved_from_cwd_and_must_match_config(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    config_path = tmp_path / "config" / "ingest-config.json"
    config_path.parent.mkdir()
    write_config(config_path, valid_config(source, "../results/"))

    loaded = load_config(config_path, cli_output="results", cwd=tmp_path)

    assert loaded.output_path == (tmp_path / "results").resolve()


def test_cli_output_mismatch_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    config_path = tmp_path / "ingest-config.json"
    write_config(config_path, valid_config(source, "expected/"))

    with pytest.raises(ConfigError, match="CLI_OUTPUT_MISMATCH"):
        load_config(config_path, cli_output="different", cwd=tmp_path)


@pytest.mark.parametrize("mount_type", ["NETWORK_SHARE", "OBJECT_STORAGE"])
def test_first_prototype_rejects_unsupported_mount_types(
    tmp_path: Path, mount_type: str
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    config = valid_config(source)
    config["source_mount"]["mount_type"] = mount_type
    config_path = tmp_path / "ingest-config.json"
    write_config(config_path, config)

    with pytest.raises(ConfigError, match="UNSUPPORTED_MOUNT_TYPE"):
        load_config(config_path)


def test_remote_file_uri_is_rejected_as_unc_input(tmp_path: Path) -> None:
    config = valid_config(tmp_path)
    config["source_mount"]["root_uri"] = "file://server/share/materials"
    config_path = tmp_path / "ingest-config.json"
    write_config(config_path, config)

    with pytest.raises(ConfigError, match="UNSUPPORTED_ROOT_URI"):
        load_config(config_path)


def test_source_mount_schema_error_includes_json_pointer(tmp_path: Path) -> None:
    config = valid_config(tmp_path)
    config["source_mount"]["source_mount_id"] = "INVALID ID"
    config_path = tmp_path / "ingest-config.json"
    write_config(config_path, config)

    with pytest.raises(ConfigError, match=r"/source_mount/source_mount_id"):
        load_config(config_path)


def test_config_and_locked_rule_versions_must_match(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    config = valid_config(source)
    config["rule_set_version"] = "ingest-rules-9.9"
    config_path = tmp_path / "ingest-config.json"
    write_config(config_path, config)

    with pytest.raises(ConfigError, match="RULE_SET_VERSION_MISMATCH"):
        load_config(config_path)


def test_rule_bundle_hashes_and_versions_are_verified() -> None:
    bundle = load_rule_bundle()

    assert bundle.rule_set_version == "ingest-rules-0.1"
    assert bundle.classification_rule_version == "artifact-classification-0.1"
    assert bundle.candidate_scoring_version == "candidate-scoring-0.1"
    assert set(bundle.documents) == {
        "ingest-rules.json",
        "artifact-classification.json",
        "candidate-scoring.json",
    }


def test_output_directory_inside_source_mount_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    config_path = tmp_path / "ingest-config.json"
    write_config(config_path, valid_config(source, "source/ingest-output/"))

    with pytest.raises(ConfigError, match="OUTPUT_INSIDE_SOURCE_ROOT"):
        load_config(config_path)


def test_full_frozen_ingest_config_fragment_is_enforced(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    config = valid_config(source)
    config["output"]["output_directory"] = "missing-trailing-slash"
    config_path = tmp_path / "ingest-config.json"
    write_config(config_path, config)

    with pytest.raises(
        ConfigError, match=r"/output/output_directory"
    ):
        load_config(config_path)
