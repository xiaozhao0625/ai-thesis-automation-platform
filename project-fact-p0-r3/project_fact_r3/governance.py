from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any

from .common import content_hash
from .extractor import extract_fixture_set


FIXED_TIME = "2026-07-15T12:00:00+08:00"

LEGAL_EVIDENCE_ROLES = {
    "EXACT_MODEL": {"PROJECT_FACT_EVIDENCE", "MODEL_PARAMETER_EVIDENCE", "GENERAL_PRINCIPLE", "BACKGROUND_ONLY"},
    "CONFIRMED_ALIAS": {"PROJECT_FACT_EVIDENCE", "MODEL_PARAMETER_EVIDENCE", "GENERAL_PRINCIPLE", "BACKGROUND_ONLY"},
    "SERIES_MATCH": {"GENERAL_PRINCIPLE", "BACKGROUND_ONLY"},
    "RELATED_MODEL": {"BACKGROUND_ONLY", "COMPARISON_ONLY"},
    "CONFLICTING_MODEL": {"REJECTED"},
}


def validate_retrieval_classification(record: dict[str, Any]) -> dict[str, Any]:
    match_type = record["match_type"]
    evidence_role = record["evidence_role"]
    if evidence_role not in LEGAL_EVIDENCE_ROLES.get(match_type, set()):
        raise ValueError(f"Illegal retrieval classification: {match_type} + {evidence_role}")
    supports_project_fact = record.get("supports_project_fact")
    supports_model_parameters = record.get("supports_model_parameters")
    if not isinstance(supports_project_fact, bool) or not isinstance(supports_model_parameters, bool):
        raise ValueError("Retrieval support flags must be explicit booleans")

    if match_type == "EXACT_MODEL":
        expected = (True, True)
    elif match_type == "CONFIRMED_ALIAS":
        alias_scope = record.get("alias_scope")
        if alias_scope not in {"PROJECT_FACT_ONLY", "PROJECT_FACT_AND_PARAMETERS"}:
            raise ValueError("Confirmed alias requires an approved alias_scope")
        expected = (True, evidence_role == "MODEL_PARAMETER_EVIDENCE")
        if expected[1] and alias_scope != "PROJECT_FACT_AND_PARAMETERS":
            raise ValueError("Confirmed alias alias_scope cannot support model parameters outside its approved scope")
    else:
        if record.get("alias_scope") is not None:
            raise ValueError("alias_scope is only valid for a confirmed alias")
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


def classify_model(locked_model: str, matched_model: str, confirmed_aliases: dict[str, str] | None = None) -> str:
    locked = locked_model.upper()
    matched = matched_model.upper()
    aliases = {key.upper(): value for key, value in (confirmed_aliases or {}).items()}
    if matched == locked:
        return "EXACT_MODEL"
    if matched in aliases and aliases[matched] in {"PROJECT_FACT_ONLY", "PROJECT_FACT_AND_PARAMETERS"}:
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


def model_token_pattern(model: str) -> re.Pattern[str]:
    prefix = re.match(r"[A-Z]+", model.upper())
    if not prefix:
        return re.compile(re.escape(model), re.I)
    return re.compile(rf"\b{re.escape(prefix.group(0))}[A-Z0-9-]+\b", re.I)


def validate_generated_surfaces(snapshot: dict[str, Any], entities: dict[str, Any], surfaces: list[dict[str, str]]) -> list[dict[str, str]]:
    issues = []
    protected_models = protected_models_from_snapshot(snapshot, entities)
    for surface in surfaces:
        for fact_key, locked_model in protected_models.items():
            for matched in model_token_pattern(locked_model).findall(surface["text"]):
                match_type = classify_model(locked_model, matched)
                if match_type == "EXACT_MODEL":
                    continue
                if surface.get("context_role") in {"BACKGROUND_ONLY", "COMPARISON_ONLY", "GENERAL_PRINCIPLE"}:
                    continue
                issues.append({
                    "issue_code": "FACT_CONSTRAINT_VIOLATION",
                    "severity": "BLOCKING",
                    "surface": surface["surface"],
                    "fact_key": fact_key,
                    "locked_model": locked_model,
                    "found_model": matched.upper(),
                    "match_type": match_type,
                })
    return issues


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
        "confirmed_by": "operator-lin-chen",
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
        version = make_version(fact["fact_id"], fact["fact_key"], next(iter(values)), links, fact_version)
        confirmed["fact_versions"].append(version)
        fact["current_fact_version_id"] = version["fact_version_id"]
        fact["status"] = "LOCKED"

    snapshot = make_snapshot(confirmed, snapshot_version)
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


def make_snapshot(entities: dict[str, Any], version: int, *, status: str = "ACTIVE") -> dict[str, Any]:
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
        "created_by": "operator-lin-chen",
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
) -> dict[str, Any]:
    resolved = deepcopy(initial_entities)
    mcu_fact = next(item for item in resolved["facts"] if item["fact_key"] == "mcu_model")
    old_version = next(item for item in resolved["fact_versions"] if item["fact_version_id"] == mcu_fact["current_fact_version_id"])
    old_version["status"] = "SUPERSEDED"
    conflict_links = [item for item in conflict_entities["source_links"] if item["fact_key"] == "mcu_model"]
    new_version = make_version(
        mcu_fact["fact_id"],
        "mcu_model",
        "STM32F103C8T6",
        conflict_links,
        old_version["version"] + 1,
        supersedes=old_version["fact_version_id"],
    )
    resolved["fact_versions"].append(new_version)
    merged_links = {item["source_link_id"]: item for item in resolved["source_links"]}
    merged_links.update({item["source_link_id"]: item for item in conflict_entities["source_links"]})
    resolved["source_links"] = sorted(merged_links.values(), key=lambda item: item["source_link_id"])
    mcu_fact["current_fact_version_id"] = new_version["fact_version_id"]
    mcu_fact["status"] = "LOCKED"
    mcu_fact["conflict_status"] = "RESOLVED"
    resolved_conflict = deepcopy(conflict_entities["conflicts"][0])
    resolved_conflict.update({
        "status": "RESOLVED",
        "resolution": {
            "decision": "APPROVED",
            "canonical_value": "STM32F103C8T6",
            "selected_source_link_ids": new_version["source_link_ids"],
            "decided_by": "operator-lin-chen",
            "decided_at": FIXED_TIME,
        },
    })
    resolved["conflicts"] = [resolved_conflict]
    new_snapshot = make_snapshot(resolved, initial_snapshot["version"] + 1)
    old_snapshot = deepcopy(initial_snapshot)
    old_snapshot["status"] = "SUPERSEDED"

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
    conflict_mcu["status"] = "CONFLICT"
    conflict_mcu["conflict_status"] = "OPEN"
    conflict_links = {item["source_link_id"]: item for item in conflict_display_entities["source_links"]}
    conflict_links.update({item["source_link_id"]: item for item in conflict_entities["source_links"]})
    conflict_display_entities["source_links"] = sorted(conflict_links.values(), key=lambda item: item["source_link_id"])
    propagated_targets, transitions = propagate_conflict(initial_targets)
    impact = summarize_impact(transitions)
    confirmation = resolve_conflict(confirmed_entities, initial_snapshot, conflict_entities, propagated_targets)

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
            "match_type": classify_model("STM32F103C8T6", matched),
            "evidence_role": role,
            "supports_project_fact": matched == "STM32F103C8T6",
            "supports_model_parameters": matched == "STM32F103C8T6",
        }
        retrieval.append(validate_retrieval_classification(record))

    return {
        "candidate": {"baseline": "v0.3.2-P0-r3", "prototype": "v1.2.4-P0-r3"},
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
        },
        "conflict": {
            "entities": conflict_display_entities,
            "snapshot": initial_snapshot,
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
