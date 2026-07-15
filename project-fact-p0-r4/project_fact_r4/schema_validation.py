from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any


def _type_matches(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, True)


def _matches(instance: Any, schema: dict[str, Any]) -> bool:
    return not validate_draft_202012_instance(instance, schema)


def validate_draft_202012_instance(instance: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Validate the Draft 2020-12 keywords used by the bundled closed schemas."""
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type:
        types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(_type_matches(instance, item) for item in types):
            return [f"{path}: expected type {types}, received {type(instance).__name__}"]
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: value {instance!r} is outside enum")
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            errors.append(f"{path}: string is shorter than minLength")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: string does not match pattern")
        if schema.get("format") == "date-time":
            try:
                datetime.fromisoformat(instance.replace("Z", "+00:00"))
            except ValueError:
                errors.append(f"{path}: invalid date-time")
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            errors.append(f"{path}: array is shorter than minItems")
        if schema.get("uniqueItems"):
            serialized = [json.dumps(item, sort_keys=True, ensure_ascii=False) for item in instance]
            if len(serialized) != len(set(serialized)):
                errors.append(f"{path}: array items are not unique")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(instance):
                errors.extend(validate_draft_202012_instance(item, item_schema, f"{path}[{index}]"))
    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required property {key}")
        if schema.get("additionalProperties") is False:
            unexpected = set(instance) - set(properties)
            for key in sorted(unexpected):
                errors.append(f"{path}: unexpected property {key}")
        for key, value in instance.items():
            if key in properties:
                errors.extend(validate_draft_202012_instance(value, properties[key], f"{path}.{key}"))
    for nested in schema.get("allOf", []):
        errors.extend(validate_draft_202012_instance(instance, nested, path))
    if "if" in schema and _matches(instance, schema["if"]):
        errors.extend(validate_draft_202012_instance(instance, schema.get("then", {}), path))
    if "oneOf" in schema:
        matched = sum(_matches(instance, branch) for branch in schema["oneOf"])
        if matched != 1:
            errors.append(f"{path}: expected exactly one oneOf branch, matched {matched}")
    return errors


def _load_schemas(schema_dir: Path) -> dict[str, dict[str, Any]]:
    return {path.name: json.loads(path.read_text(encoding="utf-8")) for path in schema_dir.glob("*.schema.json")}


def validate_review_payload_instances(payload: dict[str, Any], schema_dir: Path) -> list[str]:
    schemas = _load_schemas(schema_dir)
    errors: list[str] = []

    phases = {
        "initial": payload["initial"],
        "intake_confirmation": payload["intake_confirmation"],
        "conflict": payload["conflict"],
        "confirmation": payload["confirmation"],
    }
    for phase_name, phase in phases.items():
        entities = phase["entities"]
        for key, schema_name in {
            "facts": "project-fact.schema.json",
            "fact_versions": "project-fact-version.schema.json",
            "source_links": "fact-source-link.schema.json",
            "conflicts": "project-fact-conflict.schema.json",
        }.items():
            for index, instance in enumerate(entities.get(key, [])):
                errors.extend(validate_draft_202012_instance(instance, schemas[schema_name], f"{phase_name}.entities.{key}[{index}]"))
                if key == "source_links":
                    errors.extend(validate_draft_202012_instance(instance["locator"], schemas["source-locator.schema.json"], f"{phase_name}.entities.{key}[{index}].locator"))
        for snapshot_key in ("snapshot", "historical_snapshot", "new_snapshot"):
            snapshot = phase.get(snapshot_key)
            if snapshot:
                errors.extend(validate_draft_202012_instance(snapshot, schemas["project-fact-snapshot.schema.json"], f"{phase_name}.{snapshot_key}"))
        for index, snapshot in enumerate(phase.get("snapshots", [])):
            errors.extend(validate_draft_202012_instance(snapshot, schemas["project-fact-snapshot.schema.json"], f"{phase_name}.snapshots[{index}]"))
        for index, dependency in enumerate(phase.get("fact_dependencies", [])):
            errors.extend(validate_draft_202012_instance(dependency, schemas["fact-dependency.schema.json"], f"{phase_name}.fact_dependencies[{index}]"))
        for index, retrieval in enumerate(phase.get("retrieval", [])):
            errors.extend(validate_draft_202012_instance(retrieval, schemas["retrieval-classification.schema.json"], f"{phase_name}.retrieval[{index}]"))
        graph = phase.get("dependency_graph")
        if graph:
            errors.extend(validate_draft_202012_instance(graph, schemas["fact-dependency-graph.schema.json"], f"{phase_name}.dependency_graph"))
    return errors
