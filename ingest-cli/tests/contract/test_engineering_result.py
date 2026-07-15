from __future__ import annotations

import pytest

from thesis_ingest.contracts import ContractError, validate_instance
from thesis_ingest.engineering import can_support_success_claim


def imported_result() -> dict[str, object]:
    return {
        "schema_version": "0.1",
        "engineering_result_id": "engineering-result-imported-001",
        "result_type": "UNIT_TEST",
        "task_id": "task-001",
        "node_run_id": "node-run-001",
        "environment_snapshot": {
            "operating_system": {
                "name": "Windows",
                "version": "11",
                "architecture": "x86_64",
            },
            "runtimes": [{"name": "Python", "version": "3.11"}],
            "dependency_lock_hash": "sha256:" + "0" * 64,
            "toolchain": [{"name": "pytest", "version": "9.0.3"}],
            "hardware": [],
        },
        "input_artifact_version_ids": ["artifact-version-source-001"],
        "output_artifact_version_ids": [],
        "status": "SUCCEEDED",
        "metrics": [],
        "started_at": "2026-07-15T08:00:00Z",
        "finished_at": "2026-07-15T08:00:01Z",
        "producer": {
            "name": "external-import",
            "version": "1.0",
            "adapter_version": "ingest-cli-0.1",
        },
        "result_hash": "sha256:" + "1" * 64,
        "provenance_type": "IMPORTED",
        "provenance": {
            "source_system": "offline-ingest-cli",
            "recorded_at": "2026-07-15T08:00:01Z",
            "source_artifact_version_ids": ["artifact-version-source-001"],
        },
        "verification_status": "UNVERIFIED",
    }


def test_imported_unverified_engineering_result_matches_frozen_contract() -> None:
    validate_instance(imported_result(), "engineering-result.schema.json")


def test_imported_result_cannot_self_assert_verified_status() -> None:
    result = imported_result()
    result["verification_status"] = "VERIFIED"

    with pytest.raises(ContractError):
        validate_instance(result, "engineering-result.schema.json")


def test_imported_result_cannot_carry_trusted_execution_fields() -> None:
    result = imported_result()
    result["node_execution_attempt_id"] = "attempt-001"
    result["execution_fingerprint"] = "sha256:" + "2" * 64

    with pytest.raises(ContractError):
        validate_instance(result, "engineering-result.schema.json")


def test_imported_success_status_cannot_support_a_success_claim() -> None:
    result = imported_result()

    assert result["status"] == "SUCCEEDED"
    assert can_support_success_claim(result) is False


def test_ingest_record_id_cannot_be_used_as_artifact_version_reference() -> None:
    result = imported_result()
    result["input_artifact_version_ids"] = ["sha256:" + "a" * 64]

    with pytest.raises(ContractError):
        validate_instance(result, "engineering-result.schema.json")
