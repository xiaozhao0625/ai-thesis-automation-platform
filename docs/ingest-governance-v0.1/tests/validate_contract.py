#!/usr/bin/env python3
"""Validate the ingest-governance v0.1 documentation contract.

This is deliberately a contract test, not an ingest implementation.  It validates
the frozen documentation package supplied through ``--package`` and exits non-zero
when any delivery, JSON Schema, example, or cross-file invariant is broken.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping, NoReturn

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource


DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_VERSION = "0.1"
SHA256_ZERO = "sha256:" + "0" * 64
SHA256_ONE = "sha256:" + "1" * 64
BASELINE_FILE = "资料摄取、来源治理与工程结果统一模型研发基线_v0.1.md"
SCHEMA_FILES = (
    "source-mount.schema.json",
    "ingest-manifest.schema.json",
    "artifact-ingest-record.schema.json",
    "engineering-result.schema.json",
)
EXAMPLE_FILES = (
    "ingest-config.example.json",
    "ingest-manifest.example.json",
)
DELIVERABLE_FILES = (BASELINE_FILE, *SCHEMA_FILES, *EXAMPLE_FILES)


class ContractViolation(AssertionError):
    """Raised when a package violates a frozen contract invariant."""


class CheckReport:
    def __init__(self) -> None:
        self.check_count = 0
        self.failures: list[str] = []

    def check(self, condition: bool, message: str) -> None:
        self.check_count += 1
        if not condition:
            self.failures.append(message)

    def capture(self, label: str, operation: Any) -> Any:
        self.check_count += 1
        try:
            return operation()
        except Exception as exc:  # Contract runner must aggregate independent failures.
            self.failures.append(f"{label}: {type(exc).__name__}: {exc}")
            return None

    def assert_valid(
        self,
        validator: Draft202012Validator,
        instance: Any,
        label: str,
    ) -> bool:
        errors = sorted(validator.iter_errors(instance), key=lambda item: item.json_path)
        self.check_count += 1
        if errors:
            rendered = "; ".join(
                f"{error.json_path}: {error.message}" for error in errors[:8]
            )
            self.failures.append(f"{label} should be valid: {rendered}")
            return False
        return True

    def assert_invalid(
        self,
        validator: Draft202012Validator,
        instance: Any,
        label: str,
    ) -> None:
        errors = list(validator.iter_errors(instance))
        self.check_count += 1
        if not errors:
            self.failures.append(f"{label} should be rejected, but it validated")

    def finish(self) -> None:
        if not self.failures:
            return
        lines = [
            f"contract validation failed with {len(self.failures)} failure(s):",
            *(f"  {index}. {failure}" for index, failure in enumerate(self.failures, 1)),
        ]
        raise ContractViolation("\n".join(lines))


def _fail(message: str) -> NoReturn:
    raise ContractViolation(message)


def _reject_non_standard_number(value: str) -> NoReturn:
    raise ValueError(f"non-standard JSON numeric constant is forbidden: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def load_json_object(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 BOM is forbidden")
    text = data.decode("utf-8", errors="strict")
    value = json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_non_standard_number,
    )
    if not isinstance(value, dict):
        raise ValueError("top-level JSON value must be an object")
    return value


def require_deliverables(package: Path) -> None:
    missing = [name for name in DELIVERABLE_FILES if not (package / name).is_file()]
    empty = [
        name
        for name in DELIVERABLE_FILES
        if (package / name).is_file() and (package / name).stat().st_size == 0
    ]
    if not missing and not empty:
        return
    details: list[str] = []
    if missing:
        details.append("missing: " + ", ".join(missing))
    if empty:
        details.append("empty: " + ", ".join(empty))
    _fail(f"delivery gate failed for {package}: " + "; ".join(details))


def build_registry(
    package: Path,
    schemas: Mapping[str, dict[str, Any]],
) -> Registry:
    resources: dict[str, Resource[Any]] = {}
    for filename, schema in schemas.items():
        resource = Resource.from_contents(schema)
        resources[filename] = resource
        resources[(package / filename).resolve().as_uri()] = resource
        schema_id = schema.get("$id")
        if isinstance(schema_id, str) and schema_id:
            resources[schema_id] = resource
    return Registry().with_resources(resources.items())


def make_validator(
    schema: dict[str, Any],
    registry: Registry,
) -> Draft202012Validator:
    return Draft202012Validator(
        schema,
        registry=registry,
        format_checker=FormatChecker(),
    )


def json_pointer_escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def make_definition_validator(
    root_schema: dict[str, Any],
    definition_name: str,
    registry: Registry,
) -> Draft202012Validator:
    wrapper = {
        "$schema": DRAFT_2020_12,
        "$defs": root_schema.get("$defs", {}),
        "$ref": f"#/$defs/{json_pointer_escape(definition_name)}",
    }
    return make_validator(wrapper, registry)


def _deep_merge_schema(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(left)
    for key, value in right.items():
        if key == "required":
            merged[key] = list(dict.fromkeys([*merged.get(key, []), *value]))
        elif key == "properties" and isinstance(value, dict):
            properties = deepcopy(merged.get(key, {}))
            for property_name, property_schema in value.items():
                if (
                    property_name in properties
                    and isinstance(properties[property_name], dict)
                    and isinstance(property_schema, dict)
                ):
                    properties[property_name] = _deep_merge_schema(
                        properties[property_name], property_schema
                    )
                else:
                    properties[property_name] = deepcopy(property_schema)
            merged[key] = properties
        elif key == "$defs" and isinstance(value, dict):
            definitions = deepcopy(merged.get(key, {}))
            definitions.update(deepcopy(value))
            merged[key] = definitions
        else:
            merged[key] = deepcopy(value)
    return merged


def _resolve_local_ref(
    fragment: dict[str, Any],
    root_schema: dict[str, Any],
) -> dict[str, Any]:
    reference = fragment.get("$ref")
    if not isinstance(reference, str) or not reference.startswith("#/$defs/"):
        return fragment
    name = reference[len("#/$defs/") :].replace("~1", "/").replace("~0", "~")
    target = root_schema.get("$defs", {}).get(name)
    if not isinstance(target, dict):
        return fragment
    siblings = {key: value for key, value in fragment.items() if key != "$ref"}
    return _deep_merge_schema(target, siblings)


def _condition_matches(
    instance: Any,
    condition: dict[str, Any],
    root_schema: dict[str, Any],
) -> bool:
    wrapper = {
        "$schema": DRAFT_2020_12,
        "$defs": root_schema.get("$defs", {}),
        **condition,
    }
    return not list(Draft202012Validator(wrapper).iter_errors(instance))


def _matching_string(schema: dict[str, Any], salt: int) -> str:
    minimum = max(int(schema.get("minLength", 0)), 1)
    pattern = schema.get("pattern")
    string_format = schema.get("format")
    hex_digit = format(salt % 16, "x")
    candidates = []
    if string_format == "date-time":
        candidates.extend(
            [f"2026-07-15T00:00:{salt % 60:02d}Z", "2026-07-15T00:00:00+08:00"]
        )
    elif string_format in {"uri", "uri-reference"}:
        candidates.extend([f"file:///example/source-{salt}", f"urn:example:item:{salt}"])
    elif string_format == "date":
        candidates.append("2026-07-15")
    candidates.extend(
        [
            "sha256:" + hex_digit * 64,
            chr(ord("a") + salt % 26),
            chr(ord("A") + salt % 26),
            f"item-{salt}",
            f"ITEM_{salt}",
            f"file-{salt}.txt",
            "application/octet-stream",
        ]
    )
    try:
        compiled = re.compile(pattern) if isinstance(pattern, str) else None
    except re.error:
        compiled = None
    for candidate in candidates:
        if len(candidate) < minimum:
            candidate += "a" * (minimum - len(candidate))
        if compiled is None or compiled.search(candidate):
            return candidate
    return "a" * minimum


def _variant(value: Any, salt: int) -> Any:
    if isinstance(value, str):
        if re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            return "sha256:" + format(salt % 16, "x") * 64
        return f"{value}-{salt}"
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value + salt
    if isinstance(value, float):
        return value + float(salt)
    if isinstance(value, dict):
        result = deepcopy(value)
        for key in result:
            if key.endswith("_id") and isinstance(result[key], str):
                result[key] = _variant(result[key], salt)
                return result
        return result
    return value


def synthesize_minimal_instance(
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    *,
    salt: int = 0,
    depth: int = 0,
) -> Any:
    """Create a deterministic small candidate for a Draft 2020-12 fragment.

    Complex definitions can provide an ``examples`` entry; it is preferred.  The
    synthesizer exists so every scalar/helper definition is still exercised even
    when the package adds new ``$defs`` later.
    """

    if depth > 40:
        raise ValueError("recursive schema cannot be synthesized within 40 levels")
    fragment = _resolve_local_ref(deepcopy(schema), root_schema)
    examples = fragment.get("examples")
    if isinstance(examples, list) and examples:
        return deepcopy(examples[0])
    if "const" in fragment:
        return deepcopy(fragment["const"])
    enum = fragment.get("enum")
    if isinstance(enum, list) and enum:
        non_null = [item for item in enum if item is not None]
        return deepcopy((non_null or enum)[salt % len(non_null or enum)])

    effective = {
        key: value
        for key, value in fragment.items()
        if key not in {"allOf", "anyOf", "oneOf", "if", "then", "else"}
    }
    for branch in fragment.get("allOf", []):
        if "if" not in branch:
            effective = _deep_merge_schema(
                effective, _resolve_local_ref(branch, root_schema)
            )
    if fragment.get("oneOf"):
        effective = _deep_merge_schema(
            effective, _resolve_local_ref(fragment["oneOf"][0], root_schema)
        )
    elif fragment.get("anyOf"):
        effective = _deep_merge_schema(
            effective, _resolve_local_ref(fragment["anyOf"][0], root_schema)
        )

    expected_type = effective.get("type")
    if isinstance(expected_type, list):
        expected_type = next((item for item in expected_type if item != "null"), "null")
    if expected_type is None:
        if "properties" in effective or "required" in effective:
            expected_type = "object"
        elif "items" in effective or "prefixItems" in effective:
            expected_type = "array"
        elif "pattern" in effective or "minLength" in effective:
            expected_type = "string"

    if expected_type == "object":
        properties = effective.get("properties", {})
        instance: dict[str, Any] = {}
        required = list(effective.get("required", []))
        for property_name in required:
            property_schema = properties.get(property_name)
            if not isinstance(property_schema, dict):
                additional = effective.get("additionalProperties")
                if not isinstance(additional, dict):
                    raise ValueError(f"required property has no schema: {property_name}")
                property_schema = additional
            instance[property_name] = synthesize_minimal_instance(
                property_schema,
                root_schema,
                salt=salt,
                depth=depth + 1,
            )

        dependent_required = effective.get("dependentRequired", {})
        for trigger, dependencies in dependent_required.items():
            if trigger not in instance:
                continue
            for property_name in dependencies:
                if property_name not in instance and property_name in properties:
                    instance[property_name] = synthesize_minimal_instance(
                        properties[property_name],
                        root_schema,
                        salt=salt,
                        depth=depth + 1,
                    )

        target_size = int(effective.get("minProperties", 0))
        for property_name, property_schema in properties.items():
            if len(instance) >= target_size:
                break
            if property_name not in instance:
                instance[property_name] = synthesize_minimal_instance(
                    property_schema,
                    root_schema,
                    salt=salt,
                    depth=depth + 1,
                )
        while len(instance) < target_size:
            additional = effective.get("additionalProperties")
            if not isinstance(additional, dict):
                raise ValueError("minProperties requires typed additional properties")
            property_name = _matching_string(effective.get("propertyNames", {}), len(instance))
            instance[property_name] = synthesize_minimal_instance(
                additional,
                root_schema,
                salt=len(instance),
                depth=depth + 1,
            )

        conditional_fragments = [fragment, *fragment.get("allOf", [])]
        for conditional in conditional_fragments:
            if "if" not in conditional:
                continue
            branch_name = (
                "then"
                if _condition_matches(instance, conditional["if"], root_schema)
                else "else"
            )
            branch = conditional.get(branch_name)
            if not isinstance(branch, dict):
                continue
            branch = _resolve_local_ref(branch, root_schema)
            branch_properties = branch.get("properties", {})
            for property_name in branch.get("required", []):
                property_schema = branch_properties.get(
                    property_name, properties.get(property_name)
                )
                if isinstance(property_schema, dict):
                    instance[property_name] = synthesize_minimal_instance(
                        property_schema,
                        root_schema,
                        salt=salt,
                        depth=depth + 1,
                    )
            for property_name, property_schema in branch_properties.items():
                if "const" in property_schema:
                    instance[property_name] = deepcopy(property_schema["const"])
        return instance

    if expected_type == "array":
        minimum = int(effective.get("minItems", 0))
        if "contains" in effective:
            minimum = max(minimum, int(effective.get("minContains", 1)))
        prefix_items = effective.get("prefixItems", [])
        result: list[Any] = []
        for index, item_schema in enumerate(prefix_items):
            result.append(
                synthesize_minimal_instance(
                    item_schema,
                    root_schema,
                    salt=salt + index,
                    depth=depth + 1,
                )
            )
        item_schema = effective.get("items", {})
        while len(result) < minimum:
            value = synthesize_minimal_instance(
                item_schema,
                root_schema,
                salt=salt + len(result),
                depth=depth + 1,
            )
            if effective.get("uniqueItems") and value in result:
                value = _variant(value, salt + len(result) + 1)
            result.append(value)
        return result

    if expected_type == "string":
        return _matching_string(effective, salt)
    if expected_type == "integer":
        minimum = int(effective.get("minimum", 0))
        if "exclusiveMinimum" in effective:
            minimum = max(minimum, int(effective["exclusiveMinimum"]) + 1)
        return minimum
    if expected_type == "number":
        minimum = float(effective.get("minimum", 0))
        if "exclusiveMinimum" in effective:
            minimum = max(minimum, float(effective["exclusiveMinimum"]) + 0.5)
        return minimum
    if expected_type == "boolean":
        return False
    if expected_type == "null":
        return None
    return None


def validate_schema_headers(
    report: CheckReport,
    schemas: Mapping[str, dict[str, Any]],
) -> None:
    seen_ids: set[str] = set()
    for filename, schema in schemas.items():
        report.check(
            schema.get("$schema") == DRAFT_2020_12,
            f"{filename} must declare Draft 2020-12",
        )
        report.check(
            schema.get("$id") == filename,
            f"{filename} $id must equal its stable package filename",
        )
        report.check(
            schema.get("type") == "object",
            f"{filename} top-level type must be object",
        )
        report.check(
            schema.get("additionalProperties") is False,
            f"{filename} top-level object must be closed",
        )
        schema_id = schema.get("$id")
        report.check(
            not isinstance(schema_id, str) or schema_id not in seen_ids,
            f"duplicate schema $id: {schema_id}",
        )
        if isinstance(schema_id, str):
            seen_ids.add(schema_id)


def validate_all_definitions(
    report: CheckReport,
    schemas: Mapping[str, dict[str, Any]],
    registry: Registry,
) -> None:
    for filename, root_schema in schemas.items():
        definitions = root_schema.get("$defs", {})
        report.check(isinstance(definitions, dict), f"{filename} $defs must be an object")
        if not isinstance(definitions, dict):
            continue
        for definition_name, definition in definitions.items():
            if not isinstance(definition, dict):
                report.check(False, f"{filename} $defs.{definition_name} must be a schema")
                continue
            validator = make_definition_validator(root_schema, definition_name, registry)
            candidates = [deepcopy(item) for item in definition.get("examples", [])]
            try:
                candidates.append(synthesize_minimal_instance(definition, root_schema))
            except Exception as exc:
                report.check(
                    False,
                    f"{filename} $defs.{definition_name} has no synthesizable minimal instance: {exc}",
                )
                continue
            first_valid = next(
                (candidate for candidate in candidates if not list(validator.iter_errors(candidate))),
                None,
            )
            report.check(
                first_valid is not None,
                f"{filename} $defs.{definition_name} has no valid minimal positive instance",
            )


def extract_source_mount(config: dict[str, Any]) -> dict[str, Any]:
    source_mount = config.get("source_mount")
    if isinstance(source_mount, dict):
        return source_mount
    source_mounts = config.get("source_mounts")
    if isinstance(source_mounts, list) and len(source_mounts) == 1:
        if isinstance(source_mounts[0], dict):
            return source_mounts[0]
    _fail("ingest-config.example.json must contain one source_mount object")


def make_artifact_record(
    schema: dict[str, Any],
    *,
    record_id: str,
    relative_path: str,
    content_hash: str,
    pre_dedup_decision: str,
    pre_dedup_parser_eligible: bool,
    final_decision: str,
    final_parser_eligible: bool,
    role: str,
    duplicate_group_id: str | None = None,
) -> dict[str, Any]:
    record = synthesize_minimal_instance(schema, schema)
    if not isinstance(record, dict):
        _fail("artifact-ingest-record schema did not synthesize an object")
    record.update(
        {
            "schema_version": SCHEMA_VERSION,
            "ingest_record_id": record_id,
            "scan_id": "scan-contract-001",
            "source_mount_id": "thesis-library-2026",
            "relative_path": relative_path,
            "content_hash": content_hash,
            "source_occurrence_key": SHA256_ONE,
            "size_bytes": 128,
            "modified_at": "2026-07-15T00:00:00Z",
            "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "extension": ".docx",
            "pre_dedup_decision": pre_dedup_decision,
            "pre_dedup_parser_eligible": pre_dedup_parser_eligible,
            "ingest_decision": final_decision,
            "decision_reason_codes": {
                "ACCEPTED": [],
                "DUPLICATE": ["CONTENT_HASH_DUPLICATE"],
                "EXCLUDED": ["NOISE_DIRECTORY"],
                "QUARANTINED": ["EXECUTABLE_CONTENT"],
            }.get(final_decision, ["CLASSIFICATION_AMBIGUOUS"]),
            "parser_eligible": final_parser_eligible,
            "artifact_role": role,
            "classification_confidence": 1.0,
            "classification_method": "COMPOSITE_RULE",
            "classification_reasons": ["CONTRACT_FIXTURE"],
            "requires_review": final_decision in {"QUARANTINED", "NEEDS_REVIEW"},
            "data_classification": (
                "RESTRICTED" if final_decision == "QUARANTINED" else "INTERNAL"
            ),
            "content_categories": [],
            "access_recommendation": (
                "SECURITY_REVIEW_REQUIRED"
                if final_decision == "QUARANTINED"
                else "STANDARD"
            ),
            "model_usage_restriction": (
                "DENY_EXTERNAL_MODEL"
                if final_decision == "QUARANTINED"
                else "ALLOW"
            ),
            "rule_set_version": "ingest-rules-0.1",
            "scanner_version": "thesis-ingest-0.1",
            "observed_at": "2026-07-15T00:00:00Z",
            "issue_refs": [],
        }
    )
    if duplicate_group_id is None:
        record.pop("duplicate_group_id", None)
    else:
        record["duplicate_group_id"] = duplicate_group_id
    return record


def validate_duplicate_group_semantics(
    duplicate_group: dict[str, Any],
    records_by_id: Mapping[str, dict[str, Any]],
) -> None:
    member_ids = duplicate_group.get("member_ingest_record_ids")
    selection_status = duplicate_group.get("canonical_selection_status")
    canonical_id = duplicate_group.get("canonical_ingest_record_id")
    if not isinstance(member_ids, list) or len(member_ids) < 2:
        _fail("DuplicateGroup must reference at least two member ingest records")
    missing = [record_id for record_id in member_ids if record_id not in records_by_id]
    if missing:
        _fail("DuplicateGroup references missing ingest records: " + ", ".join(missing))
    expected_hash = duplicate_group.get("content_hash")
    if any(records_by_id[record_id].get("content_hash") != expected_hash for record_id in member_ids):
        _fail("all DuplicateGroup members must share its content_hash")
    expected_group_id = duplicate_group.get("duplicate_group_id")
    if any(
        records_by_id[record_id].get("duplicate_group_id") != expected_group_id
        for record_id in member_ids
    ):
        _fail("all DuplicateGroup members must reference its duplicate_group_id")
    canonical_candidates = {
        record_id
        for record_id in member_ids
        if records_by_id[record_id].get("pre_dedup_decision") == "ACCEPTED"
        and records_by_id[record_id].get("pre_dedup_parser_eligible") is True
    }
    if not canonical_candidates:
        if selection_status != "NO_ELIGIBLE_CANONICAL" or canonical_id is not None:
            _fail(
                "DuplicateGroup without a pre-dedup ACCEPTED + parser-eligible "
                "member must use NO_ELIGIBLE_CANONICAL without a canonical ID"
            )
        for record_id in member_ids:
            record = records_by_id[record_id]
            if record.get("ingest_decision") != record.get("pre_dedup_decision"):
                _fail("strict duplicate member disposition must remain unchanged")
        return
    if selection_status != "SELECTED":
        _fail("DuplicateGroup with eligible members must use SELECTED")
    if canonical_id not in member_ids:
        _fail("DuplicateGroup canonical_ingest_record_id must be one of its members")
    if canonical_id not in canonical_candidates:
        _fail(
            "DuplicateGroup canonical representative must come from the "
            "pre-dedup ACCEPTED + parser-eligible candidate set"
        )
    for record_id in member_ids:
        record = records_by_id[record_id]
        pre_decision = record.get("pre_dedup_decision")
        pre_parser_eligible = record.get("pre_dedup_parser_eligible")
        final_decision = record.get("ingest_decision")
        final_parser_eligible = record.get("parser_eligible")
        if record_id == canonical_id:
            if final_decision != "ACCEPTED" or final_parser_eligible is not True:
                _fail(
                    "DuplicateGroup canonical representative must finish as "
                    "ACCEPTED + parser_eligible"
                )
            continue
        if pre_decision == "ACCEPTED" and pre_parser_eligible is True:
            if final_decision != "DUPLICATE" or final_parser_eligible is not False:
                _fail(
                    "eligible non-canonical duplicate must finish as "
                    "DUPLICATE + parser_eligible false"
                )
        elif pre_decision in {"EXCLUDED", "QUARANTINED", "NEEDS_REVIEW"}:
            if final_decision != pre_decision or final_parser_eligible is not False:
                _fail(
                    f"duplicate relation must preserve stricter {pre_decision} disposal"
                )


def validate_primary_candidate_semantics(candidate: dict[str, Any]) -> None:
    status = candidate.get("recommendation_status")
    member_ids = candidate.get("candidate_ingest_record_ids")
    recommended_id = candidate.get("recommended_ingest_record_id")
    if status not in {"RECOMMENDED", "NO_RECOMMENDATION", "TIED_REVIEW"}:
        _fail(f"unsupported recommendation_status: {status}")
    if not isinstance(member_ids, list) or not member_ids:
        _fail("PrimaryArtifactCandidate must contain candidate_ingest_record_ids")
    if status == "RECOMMENDED" and not isinstance(recommended_id, str):
        _fail("RECOMMENDED requires recommended_ingest_record_id")
    if status != "RECOMMENDED" and recommended_id is not None:
        _fail(f"{status} must not force a recommended_ingest_record_id")
    if recommended_id is not None and recommended_id not in member_ids:
        _fail("recommended_ingest_record_id must reference a candidate member")
    if status == "TIED_REVIEW" and len(set(member_ids)) < 2:
        _fail("TIED_REVIEW requires at least two distinct candidates")
    if status == "TIED_REVIEW":
        tied_ids = candidate.get("tied_ingest_record_ids")
        if not isinstance(tied_ids, list) or len(set(tied_ids)) < 2:
            _fail("TIED_REVIEW requires at least two tied_ingest_record_ids")
        if not set(tied_ids).issubset(set(member_ids)):
            _fail("tied_ingest_record_ids must be candidate members")


def make_primary_candidate(
    definition: dict[str, Any],
    root_schema: dict[str, Any],
    *,
    status: str,
    include_recommended: bool,
) -> dict[str, Any]:
    candidate = synthesize_minimal_instance(definition, root_schema)
    if not isinstance(candidate, dict):
        _fail("primary_artifact_candidate did not synthesize an object")
    candidate.update(
        {
            "candidate_id": "primary-candidate-001",
            "selection_type": "PRIMARY_DOCUMENT",
            "recommendation_status": status,
            "candidate_ingest_record_ids": ["ingest-a", "ingest-b"],
            "recommendation_reasons": ["LATEST_NON_BACKUP"],
            "requires_human_confirmation": True,
        }
    )
    if include_recommended:
        candidate["recommended_ingest_record_id"] = "ingest-a"
        candidate["recommendation_score"] = 0.9
    else:
        candidate.pop("recommended_ingest_record_id", None)
        candidate.pop("recommendation_score", None)
    if status == "TIED_REVIEW":
        candidate["tied_ingest_record_ids"] = ["ingest-a", "ingest-b"]
        candidate["tied_score"] = 0.9
    else:
        candidate.pop("tied_ingest_record_ids", None)
        candidate.pop("tied_score", None)
    return candidate


def validate_policy_definitions(
    report: CheckReport,
    artifact_schema: dict[str, Any],
    artifact_validator: Draft202012Validator,
    registry: Registry,
) -> None:
    properties = artifact_schema.get("properties", {})
    report.check(
        "parser_eligible" in properties,
        "ArtifactIngestRecord must expose parser_eligible for routing and dedupe priority",
    )
    required_properties = set(artifact_schema.get("required", []))
    for property_name in (
        "pre_dedup_decision",
        "pre_dedup_parser_eligible",
        "ingest_decision",
        "parser_eligible",
    ):
        report.check(
            property_name in properties and property_name in required_properties,
            f"ArtifactIngestRecord must require {property_name}",
        )
    definitions = artifact_schema.get("$defs", {})
    report.check(
        "duplicate_group" in definitions,
        "artifact-ingest-record.schema.json must define $defs.duplicate_group",
    )
    report.check(
        "primary_artifact_candidate" in definitions,
        "artifact-ingest-record.schema.json must define $defs.primary_artifact_candidate",
    )
    if not isinstance(definitions, dict):
        return
    duplicate_definition = definitions.get("duplicate_group")
    primary_definition = definitions.get("primary_artifact_candidate")
    if not isinstance(duplicate_definition, dict) or not isinstance(primary_definition, dict):
        return

    accepted = make_artifact_record(
        artifact_schema,
        record_id="ingest-accepted",
        relative_path="project/task.docx",
        content_hash=SHA256_ONE,
        pre_dedup_decision="ACCEPTED",
        pre_dedup_parser_eligible=True,
        final_decision="ACCEPTED",
        final_parser_eligible=True,
        role="PRIMARY_REQUIREMENT",
        duplicate_group_id="duplicate-group-001",
    )
    eligible_duplicate = make_artifact_record(
        artifact_schema,
        record_id="ingest-eligible-duplicate",
        relative_path="project/task-copy.docx",
        content_hash=SHA256_ONE,
        pre_dedup_decision="ACCEPTED",
        pre_dedup_parser_eligible=True,
        final_decision="DUPLICATE",
        final_parser_eligible=False,
        role="PRIMARY_REQUIREMENT",
        duplicate_group_id="duplicate-group-001",
    )
    excluded = make_artifact_record(
        artifact_schema,
        record_id="ingest-excluded",
        relative_path="backup/task.docx",
        content_hash=SHA256_ONE,
        pre_dedup_decision="EXCLUDED",
        pre_dedup_parser_eligible=False,
        final_decision="EXCLUDED",
        final_parser_eligible=False,
        role="NOISE",
        duplicate_group_id="duplicate-group-001",
    )
    quarantined = make_artifact_record(
        artifact_schema,
        record_id="ingest-quarantined",
        relative_path="binary/tool.exe",
        content_hash=SHA256_ONE,
        pre_dedup_decision="QUARANTINED",
        pre_dedup_parser_eligible=False,
        final_decision="QUARANTINED",
        final_parser_eligible=False,
        role="EXECUTABLE",
        duplicate_group_id="duplicate-group-001",
    )
    records_by_id = {
        record["ingest_record_id"]: record
        for record in (accepted, eligible_duplicate, excluded, quarantined)
    }
    record_validity = [
        report.assert_valid(
            artifact_validator,
            record,
            f"dedupe disposition ArtifactIngestRecord {record['ingest_record_id']}",
        )
        for record in records_by_id.values()
    ]

    downgraded_excluded = deepcopy(excluded)
    downgraded_excluded["ingest_decision"] = "DUPLICATE"
    downgraded_excluded["decision_reason_codes"] = ["CONTENT_HASH_DUPLICATE"]
    report.assert_invalid(
        artifact_validator,
        downgraded_excluded,
        "pre-dedup EXCLUDED record downgraded to DUPLICATE",
    )
    downgraded_quarantine = deepcopy(quarantined)
    downgraded_quarantine["ingest_decision"] = "DUPLICATE"
    downgraded_quarantine["decision_reason_codes"] = ["CONTENT_HASH_DUPLICATE"]
    report.assert_invalid(
        artifact_validator,
        downgraded_quarantine,
        "pre-dedup QUARANTINED record downgraded to DUPLICATE",
    )

    duplicate = synthesize_minimal_instance(duplicate_definition, artifact_schema)
    if isinstance(duplicate, dict):
        duplicate.update(
            {
                "duplicate_group_id": "duplicate-group-001",
                "content_hash": SHA256_ONE,
                "canonical_selection_status": "SELECTED",
                "canonical_ingest_record_id": "ingest-accepted",
                "canonical_selection_method": "ACCEPTED_PARSER_ELIGIBLE_PATH_KEY_V1",
                "canonical_selection_reasons": ["ACCEPTED_PARSER_ELIGIBLE"],
                "member_ingest_record_ids": list(records_by_id),
            }
        )
        duplicate_validator = make_definition_validator(
            artifact_schema, "duplicate_group", registry
        )
        group_valid = report.assert_valid(
            duplicate_validator, duplicate, "DuplicateGroup positive instance"
        )
        if all(record_validity) and group_valid:
            report.capture(
                "DuplicateGroup pre-dedup ACCEPTED + parser-eligible preference",
                lambda: validate_duplicate_group_semantics(duplicate, records_by_id),
            )
            invalid_duplicate = deepcopy(duplicate)
            invalid_duplicate["canonical_ingest_record_id"] = "ingest-excluded"
            try:
                validate_duplicate_group_semantics(invalid_duplicate, records_by_id)
            except ContractViolation:
                report.check(True, "invalid duplicate representative was rejected")
            else:
                report.check(
                    False,
                    "DuplicateGroup semantic check accepted an EXCLUDED representative "
                    "despite a pre-dedup ACCEPTED + parser-eligible member",
                )

            invalid_noncanonical = deepcopy(records_by_id)
            invalid_noncanonical["ingest-eligible-duplicate"] = deepcopy(
                eligible_duplicate
            )
            invalid_noncanonical["ingest-eligible-duplicate"][
                "ingest_decision"
            ] = "ACCEPTED"
            invalid_noncanonical["ingest-eligible-duplicate"]["parser_eligible"] = True
            try:
                validate_duplicate_group_semantics(duplicate, invalid_noncanonical)
            except ContractViolation:
                report.check(True, "eligible non-canonical member disposition was enforced")
            else:
                report.check(
                    False,
                    "eligible non-canonical member was not forced to DUPLICATE + "
                    "parser_eligible false",
                )

            for strict_id in ("ingest-excluded", "ingest-quarantined"):
                invalid_strict = deepcopy(records_by_id)
                invalid_strict[strict_id] = deepcopy(invalid_strict[strict_id])
                invalid_strict[strict_id]["ingest_decision"] = "DUPLICATE"
                try:
                    validate_duplicate_group_semantics(duplicate, invalid_strict)
                except ContractViolation:
                    report.check(True, f"strict disposition preserved for {strict_id}")
                else:
                    report.check(
                        False,
                        f"DuplicateGroup lowered strict disposition for {strict_id}",
                    )

        strict_records = {
            record_id: deepcopy(records_by_id[record_id])
            for record_id in ("ingest-excluded", "ingest-quarantined")
        }
        for record in strict_records.values():
            record["duplicate_group_id"] = "duplicate-group-002"
        no_eligible = deepcopy(duplicate)
        no_eligible.update(
            {
                "duplicate_group_id": "duplicate-group-002",
                "canonical_selection_status": "NO_ELIGIBLE_CANONICAL",
                "canonical_selection_method": "NO_ELIGIBLE_CANONICAL",
                "canonical_selection_reasons": [
                    "NO_ACCEPTED_PARSER_ELIGIBLE_MEMBER"
                ],
                "member_ingest_record_ids": list(strict_records),
            }
        )
        no_eligible.pop("canonical_ingest_record_id", None)
        no_eligible_valid = report.assert_valid(
            duplicate_validator,
            no_eligible,
            "DuplicateGroup without an eligible canonical representative",
        )
        if no_eligible_valid:
            report.capture(
                "DuplicateGroup NO_ELIGIBLE_CANONICAL semantics",
                lambda: validate_duplicate_group_semantics(no_eligible, strict_records),
            )
    else:
        report.check(False, "DuplicateGroup definition must synthesize an object")

    recommendation_rule = primary_definition.get("properties", {}).get(
        "recommendation_status", {}
    )
    supported_statuses = set(recommendation_rule.get("enum", []))
    report.check(
        {"RECOMMENDED", "NO_RECOMMENDATION", "TIED_REVIEW"}.issubset(
            supported_statuses
        ),
        "PrimaryArtifactCandidate must support RECOMMENDED, NO_RECOMMENDATION, "
        "and TIED_REVIEW",
    )
    primary_validator = make_definition_validator(
        artifact_schema, "primary_artifact_candidate", registry
    )
    recommended = make_primary_candidate(
        primary_definition,
        artifact_schema,
        status="RECOMMENDED",
        include_recommended=True,
    )
    no_recommendation = make_primary_candidate(
        primary_definition,
        artifact_schema,
        status="NO_RECOMMENDATION",
        include_recommended=False,
    )
    tied_review = make_primary_candidate(
        primary_definition,
        artifact_schema,
        status="TIED_REVIEW",
        include_recommended=False,
    )
    for label, candidate in (
        ("RECOMMENDED PrimaryArtifactCandidate", recommended),
        ("NO_RECOMMENDATION without recommended ID", no_recommendation),
        ("TIED_REVIEW without recommended ID", tied_review),
    ):
        valid = report.assert_valid(primary_validator, candidate, label)
        if valid:
            report.capture(
                f"{label} semantic invariant",
                lambda candidate=candidate: validate_primary_candidate_semantics(candidate),
            )
    missing_recommendation = deepcopy(recommended)
    missing_recommendation.pop("recommended_ingest_record_id", None)
    report.assert_invalid(
        primary_validator,
        missing_recommendation,
        "RECOMMENDED without recommended_ingest_record_id",
    )


def validate_key_negative_instances(
    report: CheckReport,
    schemas: Mapping[str, dict[str, Any]],
    validators: Mapping[str, Draft202012Validator],
    source_mount: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    source_validator = validators["source-mount.schema.json"]
    manifest_validator = validators["ingest-manifest.schema.json"]
    artifact_schema = schemas["artifact-ingest-record.schema.json"]
    artifact_validator = validators["artifact-ingest-record.schema.json"]
    engineering_schema = schemas["engineering-result.schema.json"]
    engineering_validator = validators["engineering-result.schema.json"]

    extra_source = deepcopy(source_mount)
    extra_source["unexpected_contract_field"] = True
    report.assert_invalid(source_validator, extra_source, "SourceMount unknown property")
    if "root_fingerprint" in source_mount:
        invalid_source_hash = deepcopy(source_mount)
        invalid_source_hash["root_fingerprint"] = "sha256:" + "A" * 64
        report.assert_invalid(
            source_validator, invalid_source_hash, "SourceMount uppercase SHA-256"
        )
    if "last_scan_at" in source_mount:
        naive_source_time = deepcopy(source_mount)
        naive_source_time["last_scan_at"] = "2026-07-15T00:00:00"
        report.assert_invalid(
            source_validator, naive_source_time, "SourceMount timestamp without timezone"
        )

    report.check(
        manifest.get("status") == "PARTIAL",
        "ingest-manifest.example.json must demonstrate the PARTIAL contract",
    )
    report.check(
        manifest.get("root_fingerprint") is None,
        "PARTIAL Manifest example must not pretend to be a complete root snapshot",
    )
    report.check(
        manifest.get("output_hashes") == [],
        "PARTIAL Manifest example must not invent hashes for absent companion outputs",
    )
    completed_missing_finish = deepcopy(manifest)
    completed_missing_finish["status"] = "COMPLETED"
    completed_missing_finish.pop("finished_at", None)
    report.assert_invalid(
        manifest_validator,
        completed_missing_finish,
        "COMPLETED manifest without finished_at",
    )
    unknown_manifest_status = deepcopy(manifest)
    unknown_manifest_status["status"] = "DONE"
    report.assert_invalid(
        manifest_validator, unknown_manifest_status, "Manifest unknown status"
    )
    negative_count = deepcopy(manifest)
    negative_count["total_files"] = -1
    report.assert_invalid(manifest_validator, negative_count, "Manifest negative count")
    extra_manifest = deepcopy(manifest)
    extra_manifest["unexpected_contract_field"] = True
    report.assert_invalid(manifest_validator, extra_manifest, "Manifest unknown property")
    naive_manifest_time = deepcopy(manifest)
    naive_manifest_time["started_at"] = "2026-07-15T00:00:00"
    report.assert_invalid(
        manifest_validator, naive_manifest_time, "Manifest timestamp without timezone"
    )
    invalid_output_hash = deepcopy(manifest)
    invalid_output_hash["output_hashes"] = [
        {
            "relative_path": "summary.json",
            "content_hash": "sha256:1234",
            "size_bytes": 1,
            "record_count": 1,
            "schema_ref": "ingest-manifest.schema.json",
            "schema_fragment": "#/$defs/Summary",
        }
    ]
    report.assert_invalid(
        manifest_validator, invalid_output_hash, "Manifest malformed output hash"
    )

    completed_manifest = deepcopy(manifest)
    completed_manifest["status"] = "COMPLETED"
    completed_manifest["root_fingerprint"] = {
        "algorithm": "SHA-256",
        "canonicalization_version": "RFC8785-JCS-v1",
        "scope": "RECORDED_ITEMS",
        "strength": "MIXED",
        "record_count": manifest["total_files"],
        "hashed_record_count": manifest["total_files"] - 1,
        "value": SHA256_ONE,
    }
    output_routes = (
        (
            "source-mounts.json",
            "source-mount.schema.json",
            "#/$defs/SourceMountCollection",
        ),
        ("artifacts.jsonl", "artifact-ingest-record.schema.json", "#"),
        ("excluded-items.jsonl", "artifact-ingest-record.schema.json", "#"),
        (
            "duplicate-groups.jsonl",
            "artifact-ingest-record.schema.json",
            "#/$defs/duplicate_group",
        ),
        (
            "primary-candidates.jsonl",
            "artifact-ingest-record.schema.json",
            "#/$defs/primary_artifact_candidate",
        ),
        (
            "reference-candidates.jsonl",
            "artifact-ingest-record.schema.json",
            "#/$defs/reference_candidate",
        ),
        (
            "sensitive-items.jsonl",
            "artifact-ingest-record.schema.json",
            "#/$defs/sensitive_item",
        ),
        (
            "ingest-issues.jsonl",
            "artifact-ingest-record.schema.json",
            "#/$defs/ingest_issue",
        ),
        ("summary.json", "ingest-manifest.schema.json", "#/$defs/Summary"),
    )
    completed_manifest["output_hashes"] = [
        {
            "relative_path": relative_path,
            "content_hash": SHA256_ZERO,
            "size_bytes": 0,
            "record_count": 0,
            "schema_ref": schema_ref,
            "schema_fragment": schema_fragment,
        }
        for relative_path, schema_ref, schema_fragment in output_routes
    ]
    report.assert_valid(
        manifest_validator,
        completed_manifest,
        "COMPLETED Manifest with all nine frozen output routes",
    )
    misrouted_manifest = deepcopy(completed_manifest)
    misrouted_manifest["output_hashes"][0]["schema_fragment"] = "#/$defs/Summary"
    report.assert_invalid(
        manifest_validator,
        misrouted_manifest,
        "Manifest output path with mismatched schema route",
    )

    artifact = make_artifact_record(
        artifact_schema,
        record_id="ingest-negative-base",
        relative_path="project/task.docx",
        content_hash=SHA256_ZERO,
        pre_dedup_decision="ACCEPTED",
        pre_dedup_parser_eligible=True,
        final_decision="ACCEPTED",
        final_parser_eligible=True,
        role="PRIMARY_REQUIREMENT",
    )
    artifact_is_valid = report.assert_valid(
        artifact_validator, artifact, "ArtifactIngestRecord positive base"
    )
    if artifact_is_valid:
        missing_occurrence = deepcopy(artifact)
        missing_occurrence.pop("source_occurrence_key", None)
        report.assert_invalid(
            artifact_validator,
            missing_occurrence,
            "COMPUTED Artifact without source_occurrence_key",
        )

        skipped_without_rule = deepcopy(artifact)
        skipped_without_rule.update(
            {
                "hash_status": "SKIPPED_BY_POLICY",
                "pre_dedup_decision": "EXCLUDED",
                "pre_dedup_parser_eligible": False,
                "ingest_decision": "EXCLUDED",
                "decision_reason_codes": ["NOISE_DIRECTORY"],
                "decision_rule_matches": [],
                "requires_review": False,
                "parser_eligible": False,
                "artifact_role": "NOISE",
            }
        )
        skipped_without_rule.pop("content_hash", None)
        skipped_without_rule.pop("source_occurrence_key", None)
        report.assert_invalid(
            artifact_validator,
            skipped_without_rule,
            "SKIPPED_BY_POLICY Artifact without a rule match",
        )

        public_face_image = deepcopy(artifact)
        public_face_image.update(
            {
                "content_categories": ["FACE_IMAGE"],
                "data_classification": "PUBLIC",
                "access_recommendation": "STANDARD",
                "model_usage_restriction": "ALLOW",
            }
        )
        report.assert_invalid(
            artifact_validator,
            public_face_image,
            "FACE_IMAGE Artifact classified as PUBLIC",
        )
        internal_face_image = deepcopy(public_face_image)
        internal_face_image["data_classification"] = "INTERNAL"
        report.assert_valid(
            artifact_validator,
            internal_face_image,
            "FACE_IMAGE Artifact with the minimum non-PUBLIC policy",
        )

        public_database_dump = deepcopy(artifact)
        public_database_dump.update(
            {
                "pre_dedup_decision": "QUARANTINED",
                "pre_dedup_parser_eligible": False,
                "ingest_decision": "QUARANTINED",
                "decision_reason_codes": ["DATABASE_DUMP_DETECTED"],
                "requires_review": True,
                "parser_eligible": False,
                "artifact_role": "SENSITIVE_DATA",
                "content_categories": ["DATABASE_DUMP"],
                "data_classification": "PUBLIC",
                "access_recommendation": "STANDARD",
                "model_usage_restriction": "ALLOW",
            }
        )
        report.assert_invalid(
            artifact_validator,
            public_database_dump,
            "DATABASE_DUMP Artifact classified as PUBLIC",
        )
        sensitive_database_dump = deepcopy(public_database_dump)
        sensitive_database_dump["data_classification"] = "SENSITIVE"
        report.assert_valid(
            artifact_validator,
            sensitive_database_dump,
            "DATABASE_DUMP Artifact with required classification and review",
        )

        sensitive_validator = Draft202012Validator(
            {
                "$schema": DRAFT_2020_12,
                "$defs": artifact_schema["$defs"],
                "$ref": "#/$defs/sensitive_item",
            },
            format_checker=FormatChecker(),
        )
        sensitive_example = deepcopy(
            artifact_schema["$defs"]["sensitive_item"]["examples"][0]
        )
        sensitive_example.update(
            {
                "content_categories": ["FACE_IMAGE"],
                "data_classification": "INTERNAL",
                "access_recommendation": "STANDARD",
                "model_usage_restriction": "ALLOW",
            }
        )
        sensitive_example["sensitivity_reasons"][0]["category"] = "FACE_IMAGE"
        report.assert_valid(
            sensitive_validator,
            sensitive_example,
            "SensitiveItem FACE_IMAGE minimum non-PUBLIC policy",
        )
        public_sensitive_face = deepcopy(sensitive_example)
        public_sensitive_face["data_classification"] = "PUBLIC"
        report.assert_invalid(
            sensitive_validator,
            public_sensitive_face,
            "SensitiveItem FACE_IMAGE classified as PUBLIC",
        )
        sensitive_example.update(
            {
                "content_categories": ["DATABASE_DUMP"],
                "data_classification": "SENSITIVE",
            }
        )
        sensitive_example["sensitivity_reasons"][0]["category"] = "DATABASE_DUMP"
        report.assert_valid(
            sensitive_validator,
            sensitive_example,
            "SensitiveItem DATABASE_DUMP minimum classification and review",
        )
        public_source_code = deepcopy(sensitive_example)
        public_source_code.update(
            {
                "content_categories": ["SOURCE_CODE"],
                "data_classification": "PUBLIC",
                "requires_review": False,
            }
        )
        public_source_code["sensitivity_reasons"][0]["category"] = "SOURCE_CODE"
        report.assert_valid(
            sensitive_validator,
            public_source_code,
            "SensitiveItem SOURCE_CODE may remain PUBLIC",
        )

        for audit_field in (
            "pre_dedup_decision",
            "pre_dedup_parser_eligible",
        ):
            missing_audit_field = deepcopy(artifact)
            missing_audit_field.pop(audit_field, None)
            report.assert_invalid(
                artifact_validator,
                missing_audit_field,
                f"Artifact missing required {audit_field}",
            )
        for label, invalid_path in (
            ("drive-absolute relative_path", "D:/thesis/task.docx"),
            ("rooted relative_path", "/thesis/task.docx"),
            ("parent-traversal relative_path", "thesis/../task.docx"),
            ("backslash relative_path", "thesis\\task.docx"),
        ):
            invalid = deepcopy(artifact)
            invalid["relative_path"] = invalid_path
            report.assert_invalid(artifact_validator, invalid, label)
        invalid_hash = deepcopy(artifact)
        invalid_hash["content_hash"] = "sha256:" + "A" * 64
        report.assert_invalid(artifact_validator, invalid_hash, "Artifact uppercase hash")
        invalid_role = deepcopy(artifact)
        invalid_role["artifact_role"] = "DOCUMENT"
        report.assert_invalid(artifact_validator, invalid_role, "Artifact unknown role")
        invalid_decision = deepcopy(artifact)
        invalid_decision["ingest_decision"] = "DELETED"
        report.assert_invalid(
            artifact_validator, invalid_decision, "Artifact unknown ingest decision"
        )
        invalid_confidence = deepcopy(artifact)
        invalid_confidence["classification_confidence"] = 1.01
        report.assert_invalid(
            artifact_validator, invalid_confidence, "Artifact confidence over one"
        )
        extra_artifact = deepcopy(artifact)
        extra_artifact["absolute_path"] = "D:/thesis/task.docx"
        report.assert_invalid(
            artifact_validator, extra_artifact, "Artifact persisted absolute path"
        )
        duplicate_category = deepcopy(artifact)
        duplicate_category["content_categories"] = ["SOURCE_CODE", "SOURCE_CODE"]
        report.assert_invalid(
            artifact_validator, duplicate_category, "Artifact duplicate categories"
        )

    engineering = synthesize_minimal_instance(engineering_schema, engineering_schema)
    if not isinstance(engineering, dict):
        report.check(False, "EngineeringResult must synthesize an object")
        return
    engineering.update(
        {
            "schema_version": SCHEMA_VERSION,
            "engineering_result_id": "engineering-result-001",
            "result_type": "UNIT_TEST",
            "task_id": "task-001",
            "node_run_id": "node-run-001",
            "status": "SUCCEEDED",
            "started_at": "2026-07-15T00:00:00Z",
            "finished_at": "2026-07-15T00:01:00Z",
            "result_hash": SHA256_ZERO,
        }
    )
    engineering_is_valid = report.assert_valid(
        engineering_validator, engineering, "EngineeringResult positive base"
    )
    if engineering_is_valid:
        missing_provenance = deepcopy(engineering)
        missing_provenance.pop("provenance", None)
        report.assert_invalid(
            engineering_validator,
            missing_provenance,
            "EngineeringResult without provenance",
        )
        missing_finish = deepcopy(engineering)
        missing_finish.pop("finished_at", None)
        report.assert_invalid(
            engineering_validator,
            missing_finish,
            "SUCCEEDED EngineeringResult without finished_at",
        )
        invalid_result_type = deepcopy(engineering)
        invalid_result_type["result_type"] = "MAGIC_TEST"
        report.assert_invalid(
            engineering_validator,
            invalid_result_type,
            "EngineeringResult unknown result_type",
        )
        invalid_result_hash = deepcopy(engineering)
        invalid_result_hash["result_hash"] = "sha256:1234"
        report.assert_invalid(
            engineering_validator,
            invalid_result_hash,
            "EngineeringResult malformed hash",
        )
        naive_result_time = deepcopy(engineering)
        naive_result_time["started_at"] = "2026-07-15T00:00:00"
        report.assert_invalid(
            engineering_validator,
            naive_result_time,
            "EngineeringResult timestamp without timezone",
        )


def validate_cross_file_invariants(
    report: CheckReport,
    baseline_text: str,
    schemas: Mapping[str, dict[str, Any]],
    config: dict[str, Any],
    source_mount: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    report.check(
        source_mount.get("source_mount_id") == manifest.get("source_mount_id"),
        "config SourceMount and Manifest example must use the same source_mount_id",
    )
    if source_mount.get("root_fingerprint") is not None:
        report.check(
            source_mount.get("root_fingerprint") == manifest.get("root_fingerprint"),
            "config SourceMount and Manifest example root_fingerprint must match",
        )

    partitions = (
        "accepted_files",
        "excluded_files",
        "quarantined_files",
        "duplicate_files",
        "needs_review_files",
    )
    if all(isinstance(manifest.get(name), int) for name in partitions):
        report.check(
            manifest.get("total_files") == sum(manifest[name] for name in partitions),
            "Manifest total_files must equal all mutually-exclusive decision counts",
        )
    else:
        report.check(False, "Manifest example must contain every decision count")

    report.check(
        manifest.get("manifest_version") == SCHEMA_VERSION,
        "Manifest example version must be 0.1",
    )
    for filename in (
        "source-mount.schema.json",
        "artifact-ingest-record.schema.json",
        "engineering-result.schema.json",
    ):
        version_rule = schemas[filename].get("properties", {}).get("schema_version", {})
        report.check(
            version_rule.get("const") == SCHEMA_VERSION,
            f"{filename} schema_version const must be 0.1",
        )
    manifest_version_rule = schemas["ingest-manifest.schema.json"].get(
        "properties", {}
    ).get("manifest_version", {})
    report.check(
        manifest_version_rule.get("const") == SCHEMA_VERSION,
        "ingest-manifest.schema.json manifest_version const must be 0.1",
    )

    serialized_config = json.dumps(config, ensure_ascii=False)
    report.check(
        not re.search(r"[A-Za-z]:\\\\Users\\\\|[A-Za-z]:/Users/", serialized_config),
        "ingest-config.example.json must not contain a real Windows user path",
    )
    for token in (
        "ACCEPTED",
        "EXCLUDED",
        "QUARANTINED",
        "DUPLICATE",
        "pre_dedup_decision",
        "pre_dedup_parser_eligible",
        "parser_eligible",
        "canonical_ingest_record_id",
        "RECOMMENDED",
        "NO_RECOMMENDATION",
        "TIED_REVIEW",
        "recommended_ingest_record_id",
        "0 <= hashed_record_count <= record_count",
        "schema_ref + schema_fragment",
    ):
        report.check(
            token in baseline_text,
            f"baseline document must state the {token} contract",
        )


def run_contract(package: Path) -> int:
    require_deliverables(package)
    report = CheckReport()

    schemas: dict[str, dict[str, Any]] = {}
    for filename in SCHEMA_FILES:
        loaded = report.capture(
            f"parse {filename}", lambda filename=filename: load_json_object(package / filename)
        )
        if isinstance(loaded, dict):
            schemas[filename] = loaded
    examples: dict[str, dict[str, Any]] = {}
    for filename in EXAMPLE_FILES:
        loaded = report.capture(
            f"parse {filename}", lambda filename=filename: load_json_object(package / filename)
        )
        if isinstance(loaded, dict):
            examples[filename] = loaded
    if len(schemas) != len(SCHEMA_FILES) or len(examples) != len(EXAMPLE_FILES):
        report.finish()

    for filename, schema in schemas.items():
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            report.check(False, f"{filename} is not a valid Draft 2020-12 schema: {exc}")
        else:
            report.check(True, f"{filename} metaschema")

    validate_schema_headers(report, schemas)
    registry = report.capture(
        "build cross-schema registry", lambda: build_registry(package, schemas)
    )
    if not isinstance(registry, Registry):
        report.finish()
    validators = {
        filename: make_validator(schema, registry)
        for filename, schema in schemas.items()
    }

    config = examples["ingest-config.example.json"]
    manifest = examples["ingest-manifest.example.json"]
    source_mount = report.capture("extract config SourceMount", lambda: extract_source_mount(config))
    if not isinstance(source_mount, dict):
        report.finish()
    report.assert_valid(
        validators["source-mount.schema.json"],
        source_mount,
        "ingest-config.example.json embedded SourceMount",
    )
    report.assert_valid(
        validators["ingest-manifest.schema.json"],
        manifest,
        "ingest-manifest.example.json",
    )

    validate_all_definitions(report, schemas, registry)
    validate_policy_definitions(
        report,
        schemas["artifact-ingest-record.schema.json"],
        validators["artifact-ingest-record.schema.json"],
        registry,
    )
    validate_key_negative_instances(
        report,
        schemas,
        validators,
        source_mount,
        manifest,
    )
    baseline_text = (package / BASELINE_FILE).read_text(encoding="utf-8")
    validate_cross_file_invariants(
        report,
        baseline_text,
        schemas,
        config,
        source_mount,
        manifest,
    )
    report.finish()
    print(f"PASS: {report.check_count} contract checks passed for {package}")
    return 0


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the ingest-governance v0.1 baseline package"
    )
    parser.add_argument(
        "--package",
        required=True,
        type=Path,
        help="directory containing the seven formal v0.1 deliverables",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run_contract(args.package.resolve())
    except (ContractViolation, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
