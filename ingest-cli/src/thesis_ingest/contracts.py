from __future__ import annotations

import hashlib
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from thesis_ingest.canonical_json import loads_strict


class ContractError(ValueError):
    """Raised when a bundled contract or instance is invalid."""

    def __init__(self, message: str, *, pointer: str = "") -> None:
        self.pointer = pointer
        super().__init__(f"{pointer}: {message}" if pointer else message)


def package_root() -> Path:
    return Path(__file__).resolve().parents[2]


def contract_root() -> Path:
    return package_root() / "contracts" / "v0.1"


def load_schema(name: str) -> dict[str, object]:
    root = contract_root()
    lock = loads_strict((root / "contract-lock.json").read_bytes())
    if not isinstance(lock, dict):
        raise ContractError("contract lock must be an object")
    expected = lock.get("schemas", {}).get(name)
    if not isinstance(expected, str):
        raise ContractError(f"schema is not locked: {name}")
    payload = (root / name).read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise ContractError(f"contract hash mismatch: {name}")
    schema = loads_strict(payload)
    if not isinstance(schema, dict):
        raise ContractError(f"schema must be an object: {name}")
    Draft202012Validator.check_schema(schema)
    return schema


def validate_instance(
    instance: object,
    schema_name: str,
    *,
    pointer_prefix: str = "",
) -> None:
    validator = Draft202012Validator(
        load_schema(schema_name),
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
    if not errors:
        return
    error = errors[0]
    segments = "/".join(_escape_pointer(str(segment)) for segment in error.path)
    pointer = pointer_prefix.rstrip("/")
    if segments:
        pointer = f"{pointer}/{segments}"
    raise ContractError(error.message, pointer=pointer or "/")


def _escape_pointer(segment: str) -> str:
    return segment.replace("~", "~0").replace("/", "~1")
