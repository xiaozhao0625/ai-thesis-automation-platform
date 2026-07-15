from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any

from .common import content_hash
from .extractor import extract_fixture_set
from .schema_validation import validate_draft_202012_instance


FIXED_TIME = "2026-07-15T12:00:00+08:00"

LEGAL_EVIDENCE_ROLES = {
    "EXACT_MODEL": {"PROJECT_FACT_EVIDENCE", "MODEL_PARAMETER_EVIDENCE", "GENERAL_PRINCIPLE", "BACKGROUND_ONLY"},
    "CONFIRMED_ALIAS": {"PROJECT_FACT_EVIDENCE", "MODEL_PARAMETER_EVIDENCE", "GENERAL_PRINCIPLE", "BACKGROUND_ONLY"},
    "SERIES_MATCH": {"GENERAL_PRINCIPLE", "BACKGROUND_ONLY"},
    "RELATED_MODEL": {"BACKGROUND_ONLY", "COMPARISON_ONLY"},
    "CONFLICTING_MODEL": {"REJECTED"},
}

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"
FACT_ALIAS_SCHEMA = json.loads((SCHEMA_DIR / "fact-alias.schema.json").read_text(encoding="utf-8"))
PROJECT_CONTEXTS = {"PROJECT_IMPLEMENTATION", "PROJECT_FACT_OUTPUT"}
EXEMPT_CONTEXTS = {"BACKGROUND_ONLY", "COMPARISON_ONLY", "GENERAL_PRINCIPLE"}
MODEL_LIKE_TOKEN = re.compile(r"\b(?=[A-Z0-9-]*\d)[A-Z][A-Z0-9-]{2,}\b", re.I)
AUTHORIZED_APPROVERS = {"operator-lin-chen", "reviewer-zhang"}


def _require_current_alias(
    record: dict[str, Any],
    *,
    alias_registry: list[dict[str, Any]] | None,
    fact_versions: list[dict[str, Any]] | None,
    facts: list[dict[str, Any]] | None,
    active_snapshot: dict[str, Any] | None,
) -> dict[str, Any] | None:
    alias_id = record.get("alias_id")
    if alias_id is None:
        return None
    if not isinstance(alias_id, str) or not alias_id:
        raise ValueError("Alias metadata requires a non-empty alias_id")
    aliases = {item.get("alias_id"): item for item in alias_registry or []}
    alias = aliases.get(alias_id)
    if not alias:
        raise ValueError("Confirmed alias must exist in the approved FactAlias registry")
    alias_errors = validate_draft_202012_instance(alias, FACT_ALIAS_SCHEMA, "FactAlias")
    if alias_errors:
        raise ValueError("FactAlias schema validation failed: " + "; ".join(alias_errors))
    if active_snapshot is None or active_snapshot.get("status") != "ACTIVE":
        raise ValueError("Confirmed alias requires the current ACTIVE ProjectFactSnapshot")

    fact_id = record["fact_id"]
    fact_version_id = record["fact_version_id"]
    if alias["fact_id"] != fact_id or alias["fact_version_id"] != fact_version_id:
        raise ValueError("Confirmed alias does not belong to the current ProjectFactVersion")
    if alias["alias_value"].upper() != record["matched_model"].upper():
        raise ValueError("Confirmed alias value does not match the retrieved model")

    versions = {item.get("fact_version_id"): item for item in fact_versions or []}
    version = versions.get(fact_version_id)
    if not version or version.get("fact_id") != fact_id or version.get("status") != "LOCKED":
        raise ValueError("Confirmed alias must reference a LOCKED ProjectFactVersion")
    if version.get("canonical_value", "").upper() != record["locked_model"].upper():
        raise ValueError("Confirmed alias is not bound to the current locked model")

    facts_by_id = {item.get("fact_id"): item for item in facts or []}
    fact = facts_by_id.get(fact_id)
    if not fact or fact.get("status") != "LOCKED" or fact.get("current_fact_version_id") != fact_version_id:
        raise ValueError("Confirmed alias must reference the current locked ProjectFact")
    snapshot_ref = next((item for item in active_snapshot.get("facts", []) if item.get("fact_id") == fact_id), None)
    if not snapshot_ref or snapshot_ref.get("fact_version_id") != fact_version_id:
        raise ValueError("Confirmed alias is not referenced by the current ACTIVE ProjectFactSnapshot")
    return alias


def validate_retrieval_classification(
    record: dict[str, Any],
    *,
    alias_registry: list[dict[str, Any]] | None = None,
    fact_versions: list[dict[str, Any]] | None = None,
    facts: list[dict[str, Any]] | None = None,
    active_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fact_id = record.get("fact_id")
    fact_version_id = record.get("fact_version_id")
    if not isinstance(fact_id, str) or not fact_id or not isinstance(fact_version_id, str) or not fact_version_id:
        raise ValueError("Retrieval classification requires the current fact_id and fact_version_id")
    verified_alias = _require_current_alias(
        record,
        alias_registry=alias_registry,
        fact_versions=fact_versions,
        facts=facts,
        active_snapshot=active_snapshot,
    )
    computed_match_type = classify_model(
        record["locked_model"],
        record["matched_model"],
        {verified_alias["alias_value"]} if verified_alias else set(),
    )
    if record.get("match_type") != computed_match_type:
        raise ValueError(
            f"Submitted match_type {record.get('match_type')!r} does not match "
            f"server-computed match_type {computed_match_type!r}"
        )
    match_type = computed_match_type
    evidence_role = record["evidence_role"]
    if evidence_role not in LEGAL_EVIDENCE_ROLES.get(match_type, set()):
        raise ValueError(f"Illegal retrieval classification: {match_type} + {evidence_role}")
    supports_project_fact = record.get("supports_project_fact")
    supports_model_parameters = record.get("supports_model_parameters")
    if not isinstance(supports_project_fact, bool) or not isinstance(supports_model_parameters, bool):
        raise ValueError("Retrieval support flags must be explicit booleans")

    if match_type == "EXACT_MODEL":
        if record.get("alias_id") is not None or record.get("alias_scope") is not None:
            raise ValueError("Exact model evidence cannot carry alias metadata")
        expected = (True, True)
    elif match_type == "CONFIRMED_ALIAS":
        alias_scope = record.get("alias_scope")
        if alias_scope not in {"PROJECT_FACT_ONLY", "PROJECT_FACT_AND_PARAMETERS"}:
            raise ValueError("Confirmed alias requires an approved alias_scope")
        if not verified_alias:
            raise ValueError("Confirmed alias requires a verified FactAlias")
        if verified_alias["scope"] != alias_scope:
            raise ValueError("Confirmed alias scope does not match the approved FactAlias")
        expected = (True, evidence_role == "MODEL_PARAMETER_EVIDENCE")
        if expected[1] and alias_scope != "PROJECT_FACT_AND_PARAMETERS":
            raise ValueError("Confirmed alias alias_scope cannot support model parameters outside its approved scope")
    else:
        if record.get("alias_id") is not None or record.get("alias_scope") is not None:
            raise ValueError("Alias metadata is only valid for a confirmed alias")
        expected = (False, False)

    actual = (supports_project_fact, supports_model_parameters)
    if actual != expected:
        raise ValueError(f"Illegal retrieval support flags: {match_type} requires {expected}, received {actual}")
    return record


def model_series(model: str) -> str:
    upper = model.upper()
    if upper.startswith("STM32") and len(upper) >= 9:
        return upper[:9]
    return upper.split("-")[0]


def classify_model(locked_model: str, matched_model: str, verified_alias_values: set[str] | None = None) -> str:
    locked = locked_model.upper()
    matched = matched_model.upper()
    aliases = {value.upper() for value in (verified_alias_values or set())}
    if matched == locked:
        return "EXACT_MODEL"
    if matched in aliases:
        return "CONFIRMED_ALIAS"
    if model_series(matched) == model_series(locked):
        return "SERIES_MATCH"
    if matched.startswith("STM32"):
        return "RELATED_MODEL"
    return "CONFLICTING_MODEL"


def protected_models_from_snapshot(snapshot: dict[str, Any], entities: dict[str, Any]) -> dict[str, str]:
    versions = {item["fact_version_id"]: item for item in entities["fact_versions"]}
    protected: dict[str, str] = {}
    for fact_ref in snapshot["facts"]:
        fact = next(item for item in entities["facts"] if item["fact_id"] == fact_ref["fact_id"])
        if fact["fact_type"] not in {"HARDWARE_MODEL", "MODULE_MODEL"}:
            continue
        protected[fact["fact_key"]] = versions[fact_ref["fact_version_id"]]["canonical_value"]
    return protected


def validate_generated_surfaces(snapshot: dict[str, Any], entities: dict[str, Any], surfaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enforce structured bindings first; free-text token scans are secondary alarms."""
    issues: list[dict[str, Any]] = []
    protected_models = protected_models_from_snapshot(snapshot, entities)
    for surface in surfaces:
        context_role = surface.get("context_role")
        if context_role in EXEMPT_CONTEXTS:
            continue
        bindings = surface.get("fact_bindings")
        if context_role in PROJECT_CONTEXTS:
            if not isinstance(bindings, dict):
                bindings = {}
            for fact_key, locked_model in protected_models.items():
                matched = bindings.get(fact_key)
                if isinstance(matched, str) and matched.upper() == locked_model.upper():
                    continue
                issues.append({
                    "issue_code": "FACT_CONSTRAINT_VIOLATION",
                    "severity": "BLOCKING",
                    "surface": surface["surface"],
                    "fact_key": fact_key,
                    "locked_model": locked_model,
                    "found_model": matched,
                    "match_type": "MISSING_BINDING" if matched is None else classify_model(locked_model, str(matched)),
                })
            allowed_values = {value.upper() for value in protected_models.values()}
            for token in {match.upper() for match in MODEL_LIKE_TOKEN.findall(surface.get("text", ""))}:
                if token not in allowed_values:
                    issues.append({
                        "issue_code": "FACT_CONSTRAINT_VIOLATION",
                        "severity": "BLOCKING",
                        "surface": surface["surface"],
                        "fact_key": "UNBOUND_MODEL_TOKEN",
                        "locked_model": None,
                        "found_model": token,
                        "match_type": "UNBOUND_MODEL_TOKEN",
                    })
    return issues


def project_bound_outputs(snapshot: dict[str, Any], entities: dict[str, Any]) -> list[dict[str, Any]]:
    bindings = protected_models_from_snapshot(snapshot, entities)
    return [
        {
            "surface": surface,
            "context_role": "PROJECT_FACT_OUTPUT",
            "fact_bindings": bindings,
        }
        for surface in ("outline", "body", "bom", "parameter_table", "figure", "test_chapter")
    ]


def group_observations(observations: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in observations:
        grouped[item["fact_key"]].append(item)
    return dict(grouped)


def source_links(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_link_id": item["source_link_id"],
            "fact_key": item["fact_key"],
            "canonical_value": item["canonical_value"],
            "original_value": item["original_value"],
            "confidence": item["confidence"],
            "locator": item["source_locator"],
        }
        for item in observations
    ]


def make_version(
    fact_id: str,
    fact_key: str,
    canonical_value: str,
    links: list[dict[str, Any]],
    version: int,
    *,
    supersedes: str | None = None,
    confirmed_by: str = "operator-lin-chen",
) -> dict[str, Any]:
    body = {
        "fact_version_id": f"{fact_id}-v{version}",
        "fact_id": fact_id,
        "fact_key": fact_key,
        "version": version,
        "canonical_value": canonical_value,
        "status": "LOCKED",
        "locked": True,
        "source_link_ids": sorted(link["source_link_id"] for link in links if link["canonical_value"] == canonical_value),
        "supersedes_fact_version_id": supersedes,
        "confirmed_by": confirmed_by,
        "confirmed_at": FIXED_TIME,
    }
    body["content_hash"] = content_hash({
        "fact_version_id": body["fact_version_id"],
        "fact_id": fact_id,
        "canonical_value": canonical_value,
        "source_link_ids": body["source_link_ids"],
        "supersedes_fact_version_id": supersedes,
    })
    return body


def build_entities(observations: list[dict[str, Any]]) -> dict[str, Any]:
    grouped = group_observations(observations)
    links = source_links(observations)
    facts: list[dict[str, Any]] = []
    versions: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for fact_key, items in sorted(grouped.items()):
        fact_id = "fact-" + fact_key.replace("_", "-")
        values = sorted({item["canonical_value"] for item in items})
        selected = values[0] if len(values) == 1 else None
        fact = {
            "fact_id": fact_id,
            "task_id": "task-001",
            "fact_key": fact_key,
            "fact_type": items[0]["fact_type"],
            "current_fact_version_id": None,
            "status": "PROPOSED" if selected else "CONFLICT",
            "conflict_status": "NONE" if selected else "OPEN",
        }
        facts.append(fact)
        if selected:
            continue
        candidates = [
            {
                "canonical_value": value,
                "source_link_ids": sorted(item["source_link_id"] for item in items if item["canonical_value"] == value),
            }
            for value in values
        ]
        conflict_body = {
            "conflict_id": "pfc-" + fact_key.replace("_", "-"),
            "task_id": "task-001",
            "fact_id": fact_id,
            "conflict_type": "USER_MATERIAL_CONFLICT",
            "status": "OPEN",
            "candidates": candidates,
            "auto_selection_allowed": False,
            "created_at": FIXED_TIME,
        }
        conflict_body["content_hash"] = content_hash({
            "conflict_id": conflict_body["conflict_id"],
            "fact_id": fact_id,
            "candidates": candidates,
        })
        conflicts.append(conflict_body)
    return {"facts": facts, "fact_versions": versions, "source_links": links, "conflicts": conflicts}


def confirm_intake(
    proposed_entities: dict[str, Any],
    *,
    fact_version: int = 2,
    snapshot_version: int = 5,
    approved_by: str = "operator-lin-chen",
) -> dict[str, Any]:
    if proposed_entities["conflicts"]:
        raise ValueError("Cannot confirm intake while ProjectFactConflict is open")
    confirmed = deepcopy(proposed_entities)
    for fact in confirmed["facts"]:
        if fact["status"] != "PROPOSED":
            raise ValueError("Only proposed facts can be confirmed at intake")
        links = [item for item in confirmed["source_links"] if item["fact_key"] == fact["fact_key"]]
        values = {item["canonical_value"] for item in links}
        if len(values) != 1:
            raise ValueError("Intake confirmation requires one canonical value per ProjectFact")
        version = make_version(
            fact["fact_id"], fact["fact_key"], next(iter(values)), links, fact_version, confirmed_by=approved_by,
        )
        confirmed["fact_versions"].append(version)
        fact["current_fact_version_id"] = version["fact_version_id"]
        fact["status"] = "LOCKED"

    snapshot = make_snapshot(confirmed, snapshot_version, created_by=approved_by)
    approval = {
        "approval_id": f"ha-project-fact-intake-v{snapshot_version}",
        "task_id": "task-001",
        "approval_type": "PROJECT_FACT_INTAKE_CONFIRMATION",
        "status": "APPROVED",
        "snapshot_id": snapshot["snapshot_id"],
        "approved_by": approved_by,
        "approved_at": FIXED_TIME,
    }
    audit_event = {
        "audit_event_id": f"ae-project-fact-intake-v{snapshot_version}",
        "task_id": "task-001",
        "event_type": "PROJECT_FACT_INTAKE_CONFIRMED",
        "actor_id": approved_by,
        "snapshot_id": snapshot["snapshot_id"],
        "occurred_at": FIXED_TIME,
    }
    return {
        "entities": confirmed,
        "snapshot": snapshot,
        "human_approval": approval,
        "audit_event": audit_event,
    }


def make_snapshot(
    entities: dict[str, Any], version: int, *, status: str = "ACTIVE", created_by: str = "operator-lin-chen",
) -> dict[str, Any]:
    version_by_id = {item["fact_version_id"]: item for item in entities["fact_versions"]}
    refs = []
    for fact in sorted(entities["facts"], key=lambda item: item["fact_id"]):
        version_id = fact["current_fact_version_id"]
        if fact["status"] != "LOCKED" or not version_id:
            raise ValueError("ACTIVE snapshot cannot contain unlocked or conflicted facts")
        fact_version = version_by_id[version_id]
        if fact_version["status"] != "LOCKED":
            raise ValueError("ACTIVE snapshot can only reference LOCKED ProjectFactVersion objects")
        refs.append({
            "fact_id": fact["fact_id"],
            "fact_version_id": version_id,
            "canonical_value": fact_version["canonical_value"],
            "fact_version_hash": fact_version["content_hash"],
        })
    body = {
        "snapshot_id": f"pfs-task-001-v{version}",
        "task_id": "task-001",
        "version": version,
        "facts": refs,
        "status": status,
        "created_by": created_by,
        "created_at": FIXED_TIME,
    }
    body["snapshot_hash"] = content_hash({
        "snapshot_id": body["snapshot_id"],
        "task_id": body["task_id"],
        "version": version,
        "facts": refs,
    })
    return body


def execution_fingerprint(target_id: str, snapshot_hash: str, dependency_version_ids: list[str]) -> str:
    return content_hash({
        "target_id": target_id,
        "project_fact_snapshot_hash": snapshot_hash,
        "fact_version_ids": sorted(dependency_version_ids),
    })


def downstream_closure(root: str, edges: list[list[str]]) -> set[str]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for source, target in edges:
        adjacency[source].add(target)
    visited: set[str] = set()
    queue = list(adjacency.get(root, set()))
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        queue.extend(sorted(adjacency.get(current, set()) - visited))
    return visited


def dependency_targets(fact_version_id: str, snapshot_hash: str, graph: dict[str, Any]) -> list[dict[str, Any]]:
    if graph["root"] != fact_version_id:
        raise ValueError("Dependency graph root does not match the active fact version")
    closure = downstream_closure(fact_version_id, graph["edges"])
    targets = []
    for spec in graph["targets"]:
        target_type, target_id, logical_id, state = spec["target_type"], spec["target_id"], spec["logical_id"], spec["state"]
        depends_on_fact = target_id in closure
        dependencies = [fact_version_id] if depends_on_fact else []
        targets.append({
            "target_type": target_type,
            "target_id": target_id,
            "logical_id": logical_id,
            "state": state,
            "depends_on_fact": depends_on_fact,
            "fact_version_ids": dependencies,
            "execution_fingerprint": execution_fingerprint(target_id, snapshot_hash, dependencies),
        })
    return targets


def fact_dependencies(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dependencies = []
    for target in targets:
        for fact_version_id in target["fact_version_ids"]:
            dependencies.append({
                "dependency_id": f"fd-{fact_version_id}-{target['target_id']}",
                "fact_version_id": fact_version_id,
                "target_type": target["target_type"],
                "target_id": target["target_id"],
                "execution_fingerprint": target["execution_fingerprint"],
            })
    return dependencies


def propagate_conflict(targets: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    transitions = []
    updated = deepcopy(targets)
    for target in updated:
        before = target["state"]
        if not target["depends_on_fact"]:
            after = before
            reason = "NO_FACT_DEPENDENCY"
        elif before in {"SUCCEEDED", "WAITING_FOR_APPROVAL"}:
            after = "INVALIDATED"
            reason = "PROJECT_FACT_CONFLICT"
        elif before in {"READY", "QUEUED", "PENDING"}:
            after = "BLOCKED"
            reason = "PROJECT_FACT_CONFLICT"
        elif before == "RUNNING":
            after = "CANCEL_REQUESTED"
            reason = "PROJECT_FACT_CONFLICT"
            target["terminal_after_cancel"] = "BLOCKED"
        elif before == "INVALIDATED":
            after = "INVALIDATED"
            reason = "ALREADY_INVALIDATED"
        else:
            after = "BLOCKED"
            reason = "PROJECT_FACT_CONFLICT"
        target["state"] = after
        transitions.append({
            "target_type": target["target_type"],
            "target_id": target["target_id"],
            "logical_id": target["logical_id"],
            "before": before,
            "after": after,
            "reason": reason,
        })
    return updated, transitions


def summarize_impact(transitions: list[dict[str, Any]]) -> dict[str, Any]:
    result = {"invalidated": [], "blocked": [], "cancel_requested": [], "preserved": []}
    for transition in transitions:
        item = {
            "target_type": transition["target_type"],
            "target_id": transition["target_id"],
            "logical_id": transition["logical_id"],
        }
        if transition["reason"] == "NO_FACT_DEPENDENCY":
            result["preserved"].append(item)
        elif transition["after"] == "INVALIDATED":
            result["invalidated"].append(item)
        elif transition["after"] == "BLOCKED":
            result["blocked"].append(item)
        elif transition["after"] == "CANCEL_REQUESTED":
            result["cancel_requested"].append(item)
    return result


def resolve_conflict(
    initial_entities: dict[str, Any],
    initial_snapshot: dict[str, Any],
    conflict_entities: dict[str, Any],
    propagated_targets: list[dict[str, Any]],
    *,
    request: dict[str, Any],
) -> dict[str, Any]:
    if len(conflict_entities.get("conflicts", [])) != 1:
        raise ValueError("Conflict confirmation requires exactly one open ProjectFactConflict")
    conflict = conflict_entities["conflicts"][0]
    if conflict["status"] != "OPEN":
        raise ValueError("ProjectFactConflict is no longer open")
    required = {
        "conflict_id", "selected_canonical_value", "selected_source_link_ids",
        "decision", "reason", "approved_by", "impact_snapshot_hash",
    }
    missing = sorted(key for key in required if key not in request)
    if missing:
        raise ValueError("Conflict confirmation request is missing: " + ", ".join(missing))
    if request["conflict_id"] != conflict["conflict_id"]:
        raise ValueError("Conflict confirmation does not target the open ProjectFactConflict")
    if request["decision"] != "APPROVED":
        raise ValueError("Only an APPROVED conflict decision can create a new ProjectFactVersion")
    approved_by = request["approved_by"]
    if not isinstance(approved_by, str) or approved_by not in AUTHORIZED_APPROVERS:
        raise ValueError("Conflict confirmation actor is not authorized")
    if not isinstance(request["reason"], str) or not request["reason"].strip():
        raise ValueError("Conflict confirmation requires a reason")
    if request["impact_snapshot_hash"] != initial_snapshot["snapshot_hash"]:
        raise ValueError("Conflict impact snapshot is stale")

    selected_value = request["selected_canonical_value"]
    candidate = next((item for item in conflict["candidates"] if item["canonical_value"] == selected_value), None)
    if not candidate:
        raise ValueError("Selected canonical value is not a ProjectFactConflict candidate")
    selected_source_link_ids = request["selected_source_link_ids"]
    if not isinstance(selected_source_link_ids, list) or not selected_source_link_ids or len(selected_source_link_ids) != len(set(selected_source_link_ids)):
        raise ValueError("Conflict confirmation requires unique selected source links")
    if not set(selected_source_link_ids).issubset(set(candidate["source_link_ids"])):
        raise ValueError("Selected source links do not support the selected conflict candidate")
    links_by_id = {item["source_link_id"]: item for item in conflict_entities["source_links"]}
    if any(link_id not in links_by_id or links_by_id[link_id]["canonical_value"] != selected_value for link_id in selected_source_link_ids):
        raise ValueError("Selected source links do not resolve to the selected canonical value")

    resolved = deepcopy(initial_entities)
    fact = next(item for item in resolved["facts"] if item["fact_id"] == conflict["fact_id"])
    old_version = next(item for item in resolved["fact_versions"] if item["fact_version_id"] == fact["current_fact_version_id"])
    old_version["status"] = "SUPERSEDED"
    selected_links = [links_by_id[link_id] for link_id in selected_source_link_ids]
    new_version = make_version(
        fact["fact_id"],
        fact["fact_key"],
        selected_value,
        selected_links,
        old_version["version"] + 1,
        supersedes=old_version["fact_version_id"],
        confirmed_by=approved_by,
    )
    resolved["fact_versions"].append(new_version)
    merged_links = {item["source_link_id"]: item for item in resolved["source_links"]}
    merged_links.update({item["source_link_id"]: item for item in conflict_entities["source_links"]})
    resolved["source_links"] = sorted(merged_links.values(), key=lambda item: item["source_link_id"])
    fact["current_fact_version_id"] = new_version["fact_version_id"]
    fact["status"] = "LOCKED"
    fact["conflict_status"] = "RESOLVED"
    resolved_conflict = deepcopy(conflict)
    resolved_conflict.update({
        "status": "RESOLVED",
        "resolution": {
            "decision": request["decision"],
            "canonical_value": selected_value,
            "selected_source_link_ids": selected_source_link_ids,
            "reason": request["reason"].strip(),
            "impact_snapshot_hash": request["impact_snapshot_hash"],
            "decided_by": approved_by,
            "decided_at": FIXED_TIME,
        },
    })
    resolved["conflicts"] = [resolved_conflict]
    new_snapshot = make_snapshot(resolved, initial_snapshot["version"] + 1, created_by=approved_by)
    old_snapshot = deepcopy(initial_snapshot)
    old_snapshot["status"] = "SUPERSEDED"
    human_approval = {
        "approval_id": f"ha-project-fact-conflict-v{new_snapshot['version']}",
        "task_id": "task-001",
        "approval_type": "PROJECT_FACT_CONFLICT_RESOLUTION",
        "status": "APPROVED",
        "conflict_id": conflict["conflict_id"],
        "snapshot_id": new_snapshot["snapshot_id"],
        "approved_by": approved_by,
        "reason": request["reason"].strip(),
        "approved_at": FIXED_TIME,
    }
    audit_event = {
        "audit_event_id": f"ae-project-fact-conflict-v{new_snapshot['version']}",
        "task_id": "task-001",
        "event_type": "PROJECT_FACT_CONFLICT_RESOLVED",
        "actor_id": approved_by,
        "conflict_id": conflict["conflict_id"],
        "snapshot_id": new_snapshot["snapshot_id"],
        "reason": request["reason"].strip(),
        "occurred_at": FIXED_TIME,
    }

    new_outline = {
        "target_type": "NODE_RUN",
        "target_id": "nr-outline-v6",
        "logical_id": "outline_plan",
        "state": "READY",
        "depends_on_fact": True,
        "fact_version_ids": [new_version["fact_version_id"]],
        "execution_fingerprint": execution_fingerprint("nr-outline-v6", new_snapshot["snapshot_hash"], [new_version["fact_version_id"]]),
        "prior_node_run_id": "nr-outline-v5",
        "prior_node_run_state": "INVALIDATED",
    }
    downstream = []
    for target in propagated_targets:
        if target["logical_id"] in {"background_theory"}:
            downstream.append(target)
        elif target["logical_id"] == "outline_plan":
            downstream.append(new_outline)
        else:
            copy = deepcopy(target)
            if copy["state"] == "CANCEL_REQUESTED":
                copy["state"] = "BLOCKED"
            downstream.append(copy)
    return {
        "entities": resolved,
        "snapshots": [old_snapshot, new_snapshot],
        "new_snapshot": new_snapshot,
        "new_fact_version": new_version,
        "human_approval": human_approval,
        "audit_event": audit_event,
        "confirmation_request": deepcopy(request),
        "targets": downstream,
        "fact_dependencies": fact_dependencies(downstream),
        "outline_transition": {
            "old_node_run_id": "nr-outline-v5",
            "old_state": "INVALIDATED",
            "new_node_run_id": "nr-outline-v6",
            "new_state": "READY",
        },
    }


def workflow_state(targets: list[dict[str, Any]], *, phase: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for target in targets:
        if target["target_type"] != "NODE_RUN" or target["logical_id"] == "background_theory":
            continue
        state = target["state"].lower()
        result[target["logical_id"]] = {
            "runtime_status": state,
            "node_run_id": target["target_id"],
            "execution_fingerprint": target["execution_fingerprint"],
            "prior_node_run_state": target.get("prior_node_run_state"),
        }
    if phase == "proposed":
        result["project_fact_confirm"] = {"runtime_status": "ready", "node_run_id": "nr-fact-confirm-v5"}
        result["outline_plan"] = {"runtime_status": "blocked", "node_run_id": "nr-outline-v5"}
    else:
        result["project_fact_confirm"] = {
            "runtime_status": "blocked" if phase == "conflict" else "succeeded",
            "node_run_id": "nr-fact-confirm-v6" if phase == "confirmed" else "nr-fact-confirm-v5",
        }
    return result


def build_review_payload(fixtures: Path) -> dict[str, Any]:
    initial_observations = extract_fixture_set(fixtures)
    initial_entities = build_entities(initial_observations)
    if initial_entities["conflicts"]:
        raise ValueError("Primary fixture set must not contain conflicts")
    intake_confirmation = confirm_intake(initial_entities)
    confirmed_entities = intake_confirmation["entities"]
    initial_snapshot = intake_confirmation["snapshot"]
    mcu_fact = next(item for item in confirmed_entities["facts"] if item["fact_key"] == "mcu_model")
    mcu_version = next(item for item in confirmed_entities["fact_versions"] if item["fact_version_id"] == mcu_fact["current_fact_version_id"])
    dependency_graph = json.loads((fixtures / "expected/dependency-graph.json").read_text(encoding="utf-8"))
    initial_targets = dependency_targets(mcu_version["fact_version_id"], initial_snapshot["snapshot_hash"], dependency_graph)

    conflict_observations = extract_fixture_set(fixtures, conflicting_source=True)
    conflict_entities = build_entities(conflict_observations)
    if len(conflict_entities["conflicts"]) != 1:
        raise ValueError("Conflict fixture must create exactly one ProjectFactConflict")
    conflict_display_entities = deepcopy(confirmed_entities)
    conflict_mcu = next(item for item in conflict_display_entities["facts"] if item["fact_key"] == "mcu_model")
    conflict_mcu["last_locked_fact_version_id"] = conflict_mcu["current_fact_version_id"]
    conflict_mcu["current_fact_version_id"] = None
    conflict_mcu["status"] = "CONFLICT"
    conflict_mcu["conflict_status"] = "OPEN"
    conflict_links = {item["source_link_id"]: item for item in conflict_display_entities["source_links"]}
    conflict_links.update({item["source_link_id"]: item for item in conflict_entities["source_links"]})
    conflict_display_entities["source_links"] = sorted(conflict_links.values(), key=lambda item: item["source_link_id"])
    suspended_snapshot = deepcopy(initial_snapshot)
    suspended_snapshot["status"] = "SUSPENDED"
    propagated_targets, transitions = propagate_conflict(initial_targets)
    impact = summarize_impact(transitions)
    default_candidate = conflict_entities["conflicts"][0]["candidates"][0]
    default_confirmation_request = {
        "conflict_id": conflict_entities["conflicts"][0]["conflict_id"],
        "selected_canonical_value": default_candidate["canonical_value"],
        "selected_source_link_ids": default_candidate["source_link_ids"],
        "decision": "APPROVED",
        "reason": "以任务书与 BOM 的一致事实为准",
        "approved_by": "reviewer-zhang",
        "impact_snapshot_hash": initial_snapshot["snapshot_hash"],
    }
    confirmation = resolve_conflict(
        confirmed_entities,
        initial_snapshot,
        conflict_entities,
        propagated_targets,
        request=default_confirmation_request,
    )

    retrieval = []
    for matched, role in [
        ("STM32F103C8T6", "MODEL_PARAMETER_EVIDENCE"),
        ("STM32F103ZET6", "GENERAL_PRINCIPLE"),
        ("STM32F407VET6", "COMPARISON_ONLY"),
    ]:
        record = {
            "result_id": "rr-" + matched.lower(),
            "locked_model": "STM32F103C8T6",
            "matched_model": matched,
            "fact_id": mcu_fact["fact_id"],
            "fact_version_id": mcu_version["fact_version_id"],
            "alias_id": None,
            "match_type": classify_model("STM32F103C8T6", matched),
            "evidence_role": role,
            "supports_project_fact": matched == "STM32F103C8T6",
            "supports_model_parameters": matched == "STM32F103C8T6",
        }
        retrieval.append(validate_retrieval_classification(
            record,
            fact_versions=confirmed_entities["fact_versions"],
            facts=confirmed_entities["facts"],
            active_snapshot=initial_snapshot,
        ))

    return {
        "candidate": {"baseline": "v0.3.2-P0-r5", "prototype": "v1.2.4-P0-r5"},
        "initial": {
            "entities": initial_entities,
            "snapshot": None,
            "targets": [],
            "dependency_graph": dependency_graph,
            "fact_dependencies": [],
            "workflow_state": workflow_state([], phase="proposed"),
            "retrieval": [],
        },
        "intake_confirmation": {
            **intake_confirmation,
            "targets": initial_targets,
            "dependency_graph": dependency_graph,
            "fact_dependencies": fact_dependencies(initial_targets),
            "workflow_state": workflow_state(initial_targets, phase="intake_confirmed"),
            "retrieval": retrieval,
            "generated_outputs": project_bound_outputs(initial_snapshot, confirmed_entities),
        },
        "conflict": {
            "entities": conflict_display_entities,
            "snapshot": suspended_snapshot,
            "snapshot_status_transition": {
                "snapshot_id": initial_snapshot["snapshot_id"],
                "from_status": "ACTIVE",
                "to_status": "SUSPENDED",
                "occurred_at": FIXED_TIME,
            },
            "project_fact_conflict": conflict_entities["conflicts"][0],
            "targets": propagated_targets,
            "transitions": transitions,
            "impact": impact,
            "workflow_state": workflow_state(propagated_targets, phase="conflict"),
        },
        "confirmation": {
            **confirmation,
            "workflow_state": workflow_state(confirmation["targets"], phase="confirmed"),
        },
    }


def resolve_conflict_request(fixtures: Path, request: dict[str, Any]) -> dict[str, Any]:
    """Resolve the fixture conflict with a caller-supplied, validated decision."""
    payload = build_review_payload(fixtures)
    confirmation = resolve_conflict(
        payload["intake_confirmation"]["entities"],
        payload["intake_confirmation"]["snapshot"],
        {
            "conflicts": [payload["conflict"]["project_fact_conflict"]],
            "source_links": payload["conflict"]["entities"]["source_links"],
        },
        payload["conflict"]["targets"],
        request=request,
    )
    confirmation["workflow_state"] = workflow_state(confirmation["targets"], phase="confirmed")
    return confirmation
