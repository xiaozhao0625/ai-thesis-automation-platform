from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import unittest

from project_fact_r5.extractor import extract_fixture_set
from project_fact_r5.governance import (
    build_entities,
    build_review_payload,
    classify_model,
    confirm_intake,
    dependency_targets,
    downstream_closure,
    make_snapshot,
    protected_models_from_snapshot,
    resolve_conflict,
    resolve_conflict_request,
    validate_generated_surfaces,
    validate_retrieval_classification,
)
from project_fact_r5.schema_validation import validate_review_payload_instances


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def confirmation_request(payload: dict, candidate_index: int = 0, **overrides: object) -> dict:
    conflict = payload["conflict"]["project_fact_conflict"]
    candidate = conflict["candidates"][candidate_index]
    body = {
        "conflict_id": conflict["conflict_id"],
        "selected_canonical_value": candidate["canonical_value"],
        "selected_source_link_ids": candidate["source_link_ids"],
        "decision": "APPROVED",
        "reason": "以已核验的用户材料为准",
        "approved_by": "reviewer-zhang",
        "impact_snapshot_hash": payload["intake_confirmation"]["snapshot"]["snapshot_hash"],
    }
    body.update(overrides)
    return body


def open_conflict_context(payload: dict) -> dict:
    return {
        "conflicts": [payload["conflict"]["project_fact_conflict"]],
        "source_links": payload["conflict"]["entities"]["source_links"],
    }


class RetrievalConstraintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = build_review_payload(FIXTURES)
        cls.confirmed = cls.payload["intake_confirmation"]

    def context(self) -> dict:
        return {
            "fact_versions": deepcopy(self.confirmed["entities"]["fact_versions"]),
            "facts": deepcopy(self.confirmed["entities"]["facts"]),
            "active_snapshot": deepcopy(self.confirmed["snapshot"]),
        }

    def record(self, matched: str, match_type: str, role: str, **overrides: object) -> dict:
        mcu = next(item for item in self.confirmed["entities"]["facts"] if item["fact_key"] == "mcu_model")
        record = {
            "result_id": "rr-test",
            "fact_id": mcu["fact_id"],
            "fact_version_id": mcu["current_fact_version_id"],
            "locked_model": "STM32F103C8T6",
            "matched_model": matched,
            "match_type": match_type,
            "evidence_role": role,
            "alias_id": None,
            "supports_project_fact": match_type == "EXACT_MODEL",
            "supports_model_parameters": match_type == "EXACT_MODEL",
        }
        record.update(overrides)
        return record

    def alias_context(self, **overrides: object) -> tuple[dict, list[dict], dict]:
        context = self.context()
        version = next(item for item in context["fact_versions"] if item["fact_key"] == "mcu_model")
        record = self.record("STM32_ALIAS", "CONFIRMED_ALIAS", "PROJECT_FACT_EVIDENCE")
        record.update({
            "alias_id": "alias-mcu-001",
            "alias_scope": "PROJECT_FACT_ONLY",
            "supports_project_fact": True,
            "supports_model_parameters": False,
        })
        record.update(overrides)
        alias = {
            "alias_id": "alias-mcu-001",
            "fact_id": version["fact_id"],
            "fact_version_id": version["fact_version_id"],
            "alias_value": "STM32_ALIAS",
            "scope": "PROJECT_FACT_ONLY",
            "status": "APPROVED",
            "confirmed_by": "reviewer-zhang",
            "confirmed_at": "2026-07-15T12:00:00+08:00",
        }
        return record, [alias], context

    def surface(self, **overrides: str) -> dict:
        bindings = protected_models_from_snapshot(self.confirmed["snapshot"], self.confirmed["entities"])
        bindings.update(overrides)
        return {"surface": "body", "context_role": "PROJECT_IMPLEMENTATION", "fact_bindings": bindings}

    def test_exact_series_and_related_models_are_distinct(self) -> None:
        self.assertEqual(classify_model("STM32F103C8T6", "STM32F103C8T6"), "EXACT_MODEL")
        self.assertEqual(classify_model("STM32F103C8T6", "STM32F103ZET6"), "SERIES_MATCH")
        self.assertEqual(classify_model("STM32F103C8T6", "STM32F407VET6"), "RELATED_MODEL")

    def test_runtime_rejects_spoofed_exact_match(self) -> None:
        with self.assertRaisesRegex(ValueError, "server-computed match_type"):
            validate_retrieval_classification(self.record("ESP32", "EXACT_MODEL", "PROJECT_FACT_EVIDENCE", supports_project_fact=True, supports_model_parameters=True))

    def test_runtime_rejects_spoofed_series_match(self) -> None:
        with self.assertRaisesRegex(ValueError, "server-computed match_type"):
            validate_retrieval_classification(self.record("ATmega328P", "SERIES_MATCH", "GENERAL_PRINCIPLE", supports_project_fact=False, supports_model_parameters=False))

    def test_payload_retrieval_classifications_are_server_computed(self) -> None:
        self.assertEqual(
            [item["match_type"] for item in self.confirmed["retrieval"]],
            ["EXACT_MODEL", "SERIES_MATCH", "RELATED_MODEL"],
        )

    def test_non_exact_evidence_and_support_flags_remain_restricted(self) -> None:
        invalid_role = self.record("STM32F407VET6", "RELATED_MODEL", "PROJECT_FACT_EVIDENCE", supports_project_fact=False, supports_model_parameters=False)
        with self.assertRaisesRegex(ValueError, "Illegal retrieval classification"):
            validate_retrieval_classification(invalid_role)
        invalid_support = self.record("STM32F103ZET6", "SERIES_MATCH", "GENERAL_PRINCIPLE", supports_project_fact=True, supports_model_parameters=True)
        with self.assertRaisesRegex(ValueError, "support flags"):
            validate_retrieval_classification(invalid_support)

    def test_current_approved_alias_is_accepted(self) -> None:
        record, aliases, context = self.alias_context()
        self.assertEqual(validate_retrieval_classification(record, alias_registry=aliases, **context)["match_type"], "CONFIRMED_ALIAS")

    def test_alias_must_exist_and_match_fact_and_scope(self) -> None:
        record, aliases, context = self.alias_context()
        with self.assertRaisesRegex(ValueError, "FactAlias registry"):
            validate_retrieval_classification(record, alias_registry=[], **context)
        aliases[0]["fact_id"] = "fact-wireless-model"
        with self.assertRaisesRegex(ValueError, "current ProjectFactVersion"):
            validate_retrieval_classification(record, alias_registry=aliases, **context)
        record, aliases, context = self.alias_context(alias_scope="PROJECT_FACT_AND_PARAMETERS", evidence_role="MODEL_PARAMETER_EVIDENCE", supports_model_parameters=True)
        with self.assertRaisesRegex(ValueError, "scope does not match"):
            validate_retrieval_classification(record, alias_registry=aliases, **context)

    def test_alias_must_reference_current_locked_snapshot_version(self) -> None:
        record, aliases, context = self.alias_context()
        next(item for item in context["fact_versions"] if item["fact_version_id"] == record["fact_version_id"])["status"] = "SUPERSEDED"
        with self.assertRaisesRegex(ValueError, "LOCKED ProjectFactVersion"):
            validate_retrieval_classification(record, alias_registry=aliases, **context)
        record, aliases, context = self.alias_context()
        context["active_snapshot"]["facts"] = [item for item in context["active_snapshot"]["facts"] if item["fact_id"] != record["fact_id"]]
        with self.assertRaisesRegex(ValueError, "ACTIVE ProjectFactSnapshot"):
            validate_retrieval_classification(record, alias_registry=aliases, **context)

    def test_alias_must_conform_to_fact_alias_schema(self) -> None:
        record, aliases, context = self.alias_context()
        del aliases[0]["confirmed_by"]
        with self.assertRaisesRegex(ValueError, "FactAlias schema validation failed"):
            validate_retrieval_classification(record, alias_registry=aliases, **context)

    def test_structured_fact_bindings_are_the_primary_constraint(self) -> None:
        self.assertEqual(validate_generated_surfaces(self.confirmed["snapshot"], self.confirmed["entities"], self.confirmed["generated_outputs"]), [])
        missing = self.surface()
        del missing["fact_bindings"]["sensor_model"]
        issues = validate_generated_surfaces(self.confirmed["snapshot"], self.confirmed["entities"], [missing])
        self.assertTrue(any(item["fact_key"] == "sensor_model" and item["match_type"] == "MISSING_BINDING" for item in issues))

    def test_every_required_output_carries_all_current_model_bindings(self) -> None:
        required = {"mcu_model", "sensor_model", "wireless_model", "display_driver"}
        for output in self.confirmed["generated_outputs"]:
            self.assertEqual(set(output["fact_bindings"]), required, output["surface"])

    def assert_binding_blocked(self, fact_key: str, replacement: str) -> None:
        issues = validate_generated_surfaces(self.confirmed["snapshot"], self.confirmed["entities"], [self.surface(**{fact_key: replacement})])
        self.assertTrue(any(item["fact_key"] == fact_key and item["severity"] == "BLOCKING" for item in issues), replacement)

    def test_dht11_to_hdc1080_is_blocking(self) -> None:
        self.assert_binding_blocked("sensor_model", "HDC1080")

    def test_esp8266_to_hc05_is_blocking(self) -> None:
        self.assert_binding_blocked("wireless_model", "HC-05")

    def test_ssd1306_to_lcd1602_is_blocking(self) -> None:
        self.assert_binding_blocked("display_driver", "LCD1602")

    def test_stm32_to_rp2040_is_blocking(self) -> None:
        self.assert_binding_blocked("mcu_model", "RP2040")

    def test_stm32_to_gd32_is_blocking(self) -> None:
        self.assert_binding_blocked("mcu_model", "GD32F103C8T6")

    def test_dht11_to_sht31_remains_blocking(self) -> None:
        self.assert_binding_blocked("sensor_model", "SHT31")

    def test_free_text_scan_is_secondary_and_comparison_is_exempt(self) -> None:
        output = self.surface()
        output["text"] = "实现说明误写为 HDC1080。"
        issues = validate_generated_surfaces(self.confirmed["snapshot"], self.confirmed["entities"], [output])
        self.assertTrue(any(item["fact_key"] == "UNBOUND_MODEL_TOKEN" for item in issues))
        comparison = {"surface": "comparison", "context_role": "COMPARISON_ONLY", "fact_bindings": {"mcu_model": "ATmega328P"}, "text": "方案比较采用 ATmega328P。"}
        self.assertEqual(validate_generated_surfaces(self.confirmed["snapshot"], self.confirmed["entities"], [comparison]), [])


class ConflictAndVersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = build_review_payload(FIXTURES)

    def resolve(self, request: dict) -> dict:
        return resolve_conflict(
            self.payload["intake_confirmation"]["entities"],
            self.payload["intake_confirmation"]["snapshot"],
            open_conflict_context(self.payload),
            self.payload["conflict"]["targets"],
            request=request,
        )

    def test_initial_confirmation_and_conflict_state(self) -> None:
        initial, confirmed, conflict = self.payload["initial"], self.payload["intake_confirmation"], self.payload["conflict"]
        self.assertIsNone(initial["snapshot"])
        self.assertEqual(initial["entities"]["fact_versions"], [])
        self.assertEqual(confirmed["snapshot"]["status"], "ACTIVE")
        self.assertEqual(confirmed["human_approval"]["approval_type"], "PROJECT_FACT_INTAKE_CONFIRMATION")
        mcu = next(item for item in conflict["entities"]["facts"] if item["fact_key"] == "mcu_model")
        self.assertIsNone(mcu["current_fact_version_id"])
        self.assertEqual(conflict["snapshot"]["status"], "SUSPENDED")
        self.assertNotIn("historical_snapshot", conflict)
        self.assertEqual(conflict["snapshot_status_transition"]["from_status"], "ACTIVE")

    def test_conflict_candidates_and_impact_are_data_driven(self) -> None:
        conflict = self.payload["conflict"]
        self.assertEqual(
            {item["canonical_value"] for item in conflict["project_fact_conflict"]["candidates"]},
            {"STM32F103C8T6", "STM32F407VET6"},
        )
        invalidated = {(item["target_type"], item["logical_id"]) for item in conflict["impact"]["invalidated"]}
        self.assertIn(("CLAIM", "claim_mcu_design"), invalidated)
        self.assertIn(("ARTIFACT_VERSION", "retrieval_evidence"), invalidated)
        self.assertIn(("QUALITY_REPORT", "quality_report"), invalidated)
        self.assertIn(("DELIVERY_PACKAGE", "delivery_package"), invalidated)

    def test_intake_actor_propagates_to_every_audit_object(self) -> None:
        confirmation = confirm_intake(self.payload["initial"]["entities"], approved_by="reviewer-zhang")
        self.assertEqual(confirmation["human_approval"]["approved_by"], "reviewer-zhang")
        self.assertEqual(confirmation["audit_event"]["actor_id"], "reviewer-zhang")
        self.assertTrue(all(item["confirmed_by"] == "reviewer-zhang" for item in confirmation["entities"]["fact_versions"]))
        self.assertEqual(confirmation["snapshot"]["created_by"], "reviewer-zhang")

    def test_payload_instances_and_dependency_closure_are_valid(self) -> None:
        self.assertEqual(validate_review_payload_instances(self.payload, ROOT / "schemas"), [])
        transitions = {item["logical_id"]: item for item in self.payload["conflict"]["transitions"]}
        self.assertEqual(transitions["section_generate_pre_group"]["after"], "INVALIDATED")
        self.assertEqual(transitions["section_generate_ch6"]["after"], "BLOCKED")
        self.assertEqual(transitions["engineering_verify"]["after"], "CANCEL_REQUESTED")
        graph = self.payload["initial"]["dependency_graph"]
        self.assertIn("nr-ch7-v5", downstream_closure(graph["root"], graph["edges"]))
        changed = deepcopy(graph)
        changed["edges"] = [edge for edge in changed["edges"] if edge != ["nr-ch6-v5", "nr-ch7-v5"]]
        targets = dependency_targets(changed["root"], self.payload["intake_confirmation"]["snapshot"]["snapshot_hash"], changed)
        self.assertFalse(next(item for item in targets if item["logical_id"] == "section_generate_ch7")["depends_on_fact"])

    def test_conflict_confirmation_uses_selected_candidate_sources_reason_and_actor(self) -> None:
        request = confirmation_request(self.payload, 1, reason="以已提交代码配置为准")
        confirmation = self.resolve(request)
        self.assertEqual(confirmation["new_fact_version"]["canonical_value"], "STM32F407VET6")
        self.assertEqual(confirmation["new_fact_version"]["source_link_ids"], request["selected_source_link_ids"])
        self.assertEqual(confirmation["confirmation_request"], request)
        resolution = confirmation["entities"]["conflicts"][0]["resolution"]
        self.assertEqual(resolution["reason"], request["reason"])
        self.assertEqual(resolution["impact_snapshot_hash"], request["impact_snapshot_hash"])
        self.assertEqual(confirmation["human_approval"]["approved_by"], request["approved_by"])
        self.assertEqual(confirmation["audit_event"]["actor_id"], request["approved_by"])
        self.assertNotEqual(confirmation["new_snapshot"]["snapshot_hash"], self.payload["intake_confirmation"]["snapshot"]["snapshot_hash"])

    def test_conflict_confirmation_default_candidate_preserves_user_material_value(self) -> None:
        confirmation = self.resolve(confirmation_request(self.payload, 0))
        self.assertEqual(confirmation["new_fact_version"]["canonical_value"], "STM32F103C8T6")
        mcu = next(item for item in confirmation["entities"]["facts"] if item["fact_key"] == "mcu_model")
        self.assertEqual(mcu["status"], "LOCKED")

    def test_confirmation_retains_old_snapshot_and_superseded_version(self) -> None:
        confirmation = self.resolve(confirmation_request(self.payload))
        versions = {item["fact_version_id"]: item for item in confirmation["entities"]["fact_versions"]}
        self.assertEqual(versions["fact-mcu-model-v2"]["status"], "SUPERSEDED")
        self.assertEqual(confirmation["snapshots"][0]["status"], "SUPERSEDED")
        self.assertEqual(confirmation["outline_transition"], {
            "old_node_run_id": "nr-outline-v5",
            "old_state": "INVALIDATED",
            "new_node_run_id": "nr-outline-v6",
            "new_state": "READY",
        })

    def test_conflict_confirmation_rejects_invalid_request_data(self) -> None:
        cases = [
            (confirmation_request(self.payload, selected_canonical_value="GD32F103C8T6"), "not a ProjectFactConflict candidate"),
            (confirmation_request(self.payload, impact_snapshot_hash="sha256:" + "0" * 64), "snapshot is stale"),
            (confirmation_request(self.payload, approved_by="untrusted-user"), "not authorized"),
            (confirmation_request(self.payload, 0, selected_source_link_ids=self.payload["conflict"]["project_fact_conflict"]["candidates"][1]["source_link_ids"]), "do not support"),
        ]
        for request, message in cases:
            with self.assertRaisesRegex(ValueError, message):
                self.resolve(request)

    def test_conflict_confirmation_rejects_missing_reason_wrong_id_and_duplicate_sources(self) -> None:
        cases = [
            (confirmation_request(self.payload, reason=""), "requires a reason"),
            (confirmation_request(self.payload, conflict_id="pfc-other"), "does not target"),
            (confirmation_request(self.payload, selected_source_link_ids=[self.payload["conflict"]["project_fact_conflict"]["candidates"][0]["source_link_ids"][0]] * 2), "unique selected source links"),
        ]
        for request, message in cases:
            with self.assertRaisesRegex(ValueError, message):
                self.resolve(request)

    def test_conflict_confirmation_cli_helper_uses_request_body(self) -> None:
        confirmation = resolve_conflict_request(FIXTURES, confirmation_request(self.payload, 1))
        self.assertEqual(confirmation["new_fact_version"]["canonical_value"], "STM32F407VET6")
        self.assertEqual(confirmation["human_approval"]["approval_type"], "PROJECT_FACT_CONFLICT_RESOLUTION")
        self.assertEqual(confirmation["audit_event"]["event_type"], "PROJECT_FACT_CONFLICT_RESOLVED")

    def test_active_snapshot_rejects_conflicted_facts(self) -> None:
        with self.assertRaisesRegex(ValueError, "unlocked or conflicted"):
            make_snapshot(build_entities(extract_fixture_set(FIXTURES, conflicting_source=True)), 6)

    def test_ui_payload_is_regenerated_from_the_frozen_fixtures(self) -> None:
        configured = os.environ.get("PROJECT_FACT_UI_PAYLOAD")
        candidates = [Path(configured)] if configured else [ROOT.parent / "prototype/project-fact-r5.json", ROOT.parent / "uiux-prototype/project-fact-r5.json"]
        payload_path = next((path for path in candidates if path.exists()), None)
        self.assertIsNotNone(payload_path, "missing packaged prototype payload")
        self.assertEqual(json.loads(payload_path.read_text(encoding="utf-8")), self.payload)


if __name__ == "__main__":
    unittest.main()
