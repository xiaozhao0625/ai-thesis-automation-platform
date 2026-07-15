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
    schema_fragment: str | None = None,
) -> None:
    schema = load_schema(schema_name)
    if schema_fragment is not None:
        if not schema_fragment.startswith("#/"):
            raise ContractError(f"unsupported schema fragment: {schema_fragment}")
        _resolve_fragment(schema, schema_fragment)
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": schema_fragment,
            "$defs": schema.get("$defs", {}),
        }
    validator = Draft202012Validator(
        schema,
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


def _resolve_fragment(schema: dict[str, object], fragment: str) -> object:
    current: object = schema
    for encoded in fragment[2:].split("/"):
        segment = encoded.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or segment not in current:
            raise ContractError(f"schema fragment not found: {fragment}")
        current = current[segment]
    return current
