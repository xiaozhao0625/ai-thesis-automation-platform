from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
from urllib.parse import unquote, urlparse

from thesis_ingest.canonical_json import CanonicalJsonError, loads_strict
from thesis_ingest.contracts import ContractError, contract_root, validate_instance


class ConfigError(ValueError):
    """Raised when an ingest configuration is invalid or unsafe."""


@dataclass(frozen=True)
class IngestConfig:
    config_path: Path
    root_path: Path
    output_path: Path
    raw: dict[str, object]
    rule_bundle: "RuleBundle"


@dataclass(frozen=True)
class RuleBundle:
    rule_set_version: str
    classification_rule_version: str
    candidate_scoring_version: str
    documents: dict[str, object]


def load_config(
    path: str | Path,
    *,
    cli_output: str | Path | None = None,
    cwd: str | Path | None = None,
) -> IngestConfig:
    config_path = Path(path).resolve()
    try:
        raw = loads_strict(config_path.read_bytes())
    except (OSError, CanonicalJsonError) as exc:
        raise ConfigError(f"CONFIG_READ_FAILED: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("CONFIG_INVALID: root must be an object")
    if raw.get("config_version") != "0.1":
        raise ConfigError("CONFIG_VERSION_MISMATCH: expected 0.1")

    source_mount = raw.get("source_mount")
    if not isinstance(source_mount, dict):
        raise ConfigError("CONFIG_INVALID: /source_mount must be an object")
    try:
        validate_instance(
            source_mount,
            "source-mount.schema.json",
            pointer_prefix="/source_mount",
        )
    except ContractError as exc:
        raise ConfigError(f"CONFIG_SCHEMA_INVALID: {exc}") from exc

    if source_mount.get("mount_type") != "LOCAL_DIRECTORY":
        raise ConfigError(
            "UNSUPPORTED_MOUNT_TYPE: only LOCAL_DIRECTORY is supported in v0.1"
        )
    root_path = _local_path_from_file_uri(source_mount.get("root_uri"))
    if not root_path.is_dir():
        raise ConfigError(f"SOURCE_ROOT_NOT_FOUND: {root_path}")

    output = raw.get("output")
    if not isinstance(output, dict):
        raise ConfigError("CONFIG_INVALID: /output must be an object")
    output_value = output.get("output_directory")
    if not isinstance(output_value, str) or not output_value:
        raise ConfigError("CONFIG_INVALID: /output/output_directory is required")
    output_path = _resolve_path(output_value, config_path.parent)
    if cli_output is not None:
        cli_path = _resolve_path(cli_output, Path(cwd or os.getcwd()))
        if cli_path != output_path:
            raise ConfigError(
                f"CLI_OUTPUT_MISMATCH: configured {output_path}, requested {cli_path}"
            )
    if output_path == root_path or root_path in output_path.parents:
        raise ConfigError(
            "OUTPUT_INSIDE_SOURCE_ROOT: output must be outside the SourceMount root"
        )

    bundle = load_rule_bundle()
    if raw.get("rule_set_version") != bundle.rule_set_version:
        raise ConfigError("RULE_SET_VERSION_MISMATCH")
    capability_pack = raw.get("capability_pack")
    if not isinstance(capability_pack, dict):
        raise ConfigError("CONFIG_INVALID: /capability_pack must be an object")
    if (
        capability_pack.get("classification_rule_version")
        != bundle.classification_rule_version
    ):
        raise ConfigError("CLASSIFICATION_RULE_VERSION_MISMATCH")
    if source_mount.get("schema_version") != "0.1":
        raise ConfigError("CONTRACT_VERSION_MISMATCH")
    if raw.get("path_normalization_version") != source_mount.get(
        "path_normalization_version"
    ):
        raise ConfigError("PATH_NORMALIZATION_VERSION_MISMATCH")
    if raw.get("hash_algorithm") != "SHA-256":
        raise ConfigError("UNSUPPORTED_HASH_ALGORITHM")

    return IngestConfig(
        config_path=config_path,
        root_path=root_path,
        output_path=output_path,
        raw=raw,
        rule_bundle=bundle,
    )


def load_rule_bundle() -> RuleBundle:
    root = Path(__file__).resolve().parents[2] / "rules" / "v0.1"
    try:
        lock = loads_strict((root / "rule-lock.json").read_bytes())
    except (OSError, CanonicalJsonError) as exc:
        raise ConfigError(f"RULE_LOCK_INVALID: {exc}") from exc
    if not isinstance(lock, dict):
        raise ConfigError("RULE_LOCK_INVALID: root must be an object")
    if lock.get("hash_algorithm") != "sha256":
        raise ConfigError("RULE_LOCK_INVALID: hash algorithm")
    versions = lock.get("versions")
    expected_documents = lock.get("documents")
    if not isinstance(versions, dict) or not isinstance(expected_documents, dict):
        raise ConfigError("RULE_LOCK_INVALID: missing versions or documents")

    documents: dict[str, object] = {}
    for name, expected_hash in expected_documents.items():
        if not isinstance(name, str) or not isinstance(expected_hash, str):
            raise ConfigError("RULE_LOCK_INVALID: invalid document hash entry")
        payload = (root / name).read_bytes()
        if hashlib.sha256(payload).hexdigest() != expected_hash:
            raise ConfigError(f"RULE_DOCUMENT_HASH_MISMATCH: {name}")
        documents[name] = loads_strict(payload)

    return RuleBundle(
        rule_set_version=_required_version(versions, "rule_set_version"),
        classification_rule_version=_required_version(
            versions, "classification_rule_version"
        ),
        candidate_scoring_version=_required_version(
            versions, "candidate_scoring_version"
        ),
        documents=documents,
    )


def _required_version(versions: dict[object, object], name: str) -> str:
    value = versions.get(name)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"RULE_LOCK_INVALID: missing {name}")
    return value


def _resolve_path(value: str | Path, base: Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve()


def _local_path_from_file_uri(value: object) -> Path:
    if not isinstance(value, str):
        raise ConfigError("UNSUPPORTED_ROOT_URI: root_uri must be a file URI")
    parsed = urlparse(value)
    if parsed.scheme.lower() != "file" or parsed.netloc:
        raise ConfigError(
            "UNSUPPORTED_ROOT_URI: only local file URIs without UNC authority are supported"
        )
    decoded = unquote(parsed.path)
    if os.name == "nt" and re.match(r"^/[A-Za-z]:/", decoded):
        decoded = decoded[1:]
    if not decoded:
        raise ConfigError("UNSUPPORTED_ROOT_URI: empty local path")
    return Path(decoded).resolve()
