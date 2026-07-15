from __future__ import annotations

from pathlib import Path

import pytest

from thesis_ingest.config import load_rule_bundle
from thesis_ingest.preflight import PreflightInput, evaluate_preflight


RULES = load_rule_bundle()
pytestmark = pytest.mark.security


def item(
    tmp_path: Path,
    relative_path: str,
    payload: bytes = b"plain text",
    *,
    discovery_excluded: bool = False,
    path_collision: bool = False,
) -> PreflightInput:
    physical = tmp_path / relative_path.replace("/", "_")
    physical.write_bytes(payload)
    return PreflightInput(
        physical_path=physical,
        relative_path=relative_path,
        discovery_excluded=discovery_excluded,
        path_collision=path_collision,
    )


@pytest.mark.parametrize(
    "relative_path",
    [
        ".venv/Lib/site.py",
        "venv/lib/site.py",
        "node_modules/pkg/index.js",
        "project/__pycache__/main.pyc",
    ],
)
def test_discovery_excluded_dependencies_are_excluded(
    tmp_path: Path, relative_path: str
) -> None:
    result = evaluate_preflight(
        item(tmp_path, relative_path, discovery_excluded=True), RULES
    )

    assert result.decision == "EXCLUDED"
    assert result.parser_eligible is False
    assert "DIRECTORY_EXCLUDED" in result.reason_codes


def test_third_party_dependency_pdf_never_enters_parser(tmp_path: Path) -> None:
    result = evaluate_preflight(
        item(tmp_path, "vendor/device/datasheet.pdf", b"%PDF-safe"), RULES
    )

    assert result.decision == "EXCLUDED"
    assert result.parser_eligible is False
    assert "THIRD_PARTY_DEPENDENCY" in result.reason_codes


@pytest.mark.parametrize("extension", [".exe", ".dll", ".bat", ".cmd", ".ps1", ".jar"])
def test_executables_and_scripts_are_quarantined(
    tmp_path: Path, extension: str
) -> None:
    result = evaluate_preflight(
        item(tmp_path, f"tools/run{extension}", b"safe inert fixture"), RULES
    )

    assert result.decision == "QUARANTINED"
    assert result.parser_eligible is False
    assert result.requires_review is True
    assert "EXECUTABLE_EXTENSION" in result.reason_codes


def test_executable_signature_overrides_backup_name_exclusion(tmp_path: Path) -> None:
    result = evaluate_preflight(
        item(tmp_path, "backup/tool.exe.bak", b"MZ\x00\x00safe fixture"), RULES
    )

    assert result.decision == "QUARANTINED"
    assert "EXECUTABLE_SIGNATURE" in result.reason_codes


@pytest.mark.parametrize(
    "relative_path",
    ["backup/full.dump", "database/prod-backup.sql", "data/users.sqlite3"],
)
def test_database_dumps_are_quarantined(
    tmp_path: Path, relative_path: str
) -> None:
    result = evaluate_preflight(item(tmp_path, relative_path), RULES)

    assert result.decision == "QUARANTINED"
    assert "DATABASE_DUMP_RISK" in result.reason_codes


def test_migration_sql_is_accepted_as_engineering_material(tmp_path: Path) -> None:
    result = evaluate_preflight(
        item(tmp_path, "migrations/001_create_users.sql", b"CREATE TABLE users();"),
        RULES,
        classification_confidence=0.8,
    )

    assert result.decision == "ACCEPTED"
    assert result.parser_eligible is True


@pytest.mark.parametrize(
    "relative_path",
    [".env", "config/secrets.json", "keys/id_rsa", "config/password.txt"],
)
def test_credential_risk_files_are_quarantined(
    tmp_path: Path, relative_path: str
) -> None:
    result = evaluate_preflight(item(tmp_path, relative_path), RULES)

    assert result.decision == "QUARANTINED"
    assert "CREDENTIAL_RISK" in result.reason_codes


@pytest.mark.parametrize("relative_path", ["draft.docx.bak", "~$draft.docx", "main.py~"])
def test_backup_and_autosave_files_are_excluded(
    tmp_path: Path, relative_path: str
) -> None:
    result = evaluate_preflight(item(tmp_path, relative_path), RULES)

    assert result.decision == "EXCLUDED"
    assert result.parser_eligible is False
    assert "BACKUP_OR_AUTOSAVE" in result.reason_codes


def test_unknown_binary_is_quarantined(tmp_path: Path) -> None:
    result = evaluate_preflight(
        item(tmp_path, "unknown/blob.xyz", b"\x00\x01\x02\x03"), RULES
    )

    assert result.decision == "QUARANTINED"
    assert "UNKNOWN_BINARY" in result.reason_codes


def test_low_confidence_text_is_needs_review(tmp_path: Path) -> None:
    result = evaluate_preflight(
        item(tmp_path, "unknown/readme.xyz", b"readable text"),
        RULES,
        classification_confidence=0.3,
    )

    assert result.decision == "NEEDS_REVIEW"
    assert result.requires_review is True
    assert result.parser_eligible is False


def test_normal_source_is_accepted(tmp_path: Path) -> None:
    result = evaluate_preflight(
        item(tmp_path, "src/main.py", b"print('ok')"),
        RULES,
        classification_confidence=0.7,
    )

    assert result.decision == "ACCEPTED"
    assert result.parser_eligible is True


def test_path_normalization_collision_is_logically_quarantined(
    tmp_path: Path,
) -> None:
    result = evaluate_preflight(
        item(tmp_path, "README.txt", path_collision=True), RULES
    )

    assert result.decision == "QUARANTINED"
    assert result.reason_codes == ("PATH_NORMALIZATION_COLLISION",)


def test_result_always_has_exactly_one_primary_disposition(tmp_path: Path) -> None:
    result = evaluate_preflight(item(tmp_path, "src/main.py"), RULES)

    assert result.decision in {
        "ACCEPTED",
        "EXCLUDED",
        "QUARANTINED",
        "NEEDS_REVIEW",
    }
    assert isinstance(result.decision, str)
