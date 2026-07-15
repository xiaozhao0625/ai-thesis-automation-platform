from __future__ import annotations

import unittest
from pathlib import Path
import json
import os
from copy import deepcopy

from project_fact_r4.governance import (
    build_entities,
    build_review_payload,
    classify_model,
    confirm_intake,
    dependency_targets,
    downstream_closure,
    make_snapshot,
    protected_models_from_snapshot,
    validate_generated_surfaces,
    validate_retrieval_classification,
)
from project_fact_r4.extractor import extract_fixture_set
from project_fact_r4.schema_validation import validate_review_payload_instances


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


class RetrievalConstraintTests(unittest.TestCase):
    def valid_record(self, match_type: str, evidence_role: str, **overrides: object) -> dict[str, object]:
        supports = match_type == "EXACT_MODEL"
        record: dict[str, object] = {
            "fact_id": "fact-mcu-model",
            "fact_version_id": "fact-mcu-model-v2",
            "locked_model": "STM32F103C8T6",
            "matched_model": "STM32F103C8T6",
            "match_type": match_type,
            "evidence_role": evidence_role,
            "alias_id": None,
            "supports_project_fact": supports,
            "supports_model_parameters": supports,
        }
        record.update(overrides)
        return record

    def approved_alias(self, **overrides: object) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
        record: dict[str, object] = {
            "fact_id": "fact-mcu-model",
            "fact_version_id": "fact-mcu-model-v2",
            "locked_model": "STM32F103C8T6",
            "matched_model": "STM32_ALIAS",
            "match_type": "CONFIRMED_ALIAS",
            "evidence_role": "PROJECT_FACT_EVIDENCE",
            "alias_id": "alias-mcu-001",
            "alias_scope": "PROJECT_FACT_ONLY",
            "supports_project_fact": True,
            "supports_model_parameters": False,
        }
        record.update(overrides)
        aliases = [{
            "alias_id": "alias-mcu-001",
            "fact_id": "fact-mcu-model",
            "fact_version_id": "fact-mcu-model-v2",
            "alias_value": "STM32_ALIAS",
            "scope": "PROJECT_FACT_ONLY",
            "status": "APPROVED",
        }]
        versions = [{
            "fact_version_id": "fact-mcu-model-v2",
            "fact_id": "fact-mcu-model",
            "canonical_value": "STM32F103C8T6",
        }]
        return record, aliases, versions

    def test_exact_series_and_related_models_are_distinct(self) -> None:
        self.assertEqual(classify_model("STM32F103C8T6", "STM32F103C8T6"), "EXACT_MODEL")
        self.assertEqual(classify_model("STM32F103C8T6", "STM32F103ZET6"), "SERIES_MATCH")
        self.assertEqual(classify_model("STM32F103C8T6", "STM32F407VET6"), "RELATED_MODEL")

    def test_related_model_cannot_be_project_fact_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "Illegal retrieval classification"):
            validate_retrieval_classification({
                "fact_id": "fact-mcu-model",
                "fact_version_id": "fact-mcu-model-v2",
                "locked_model": "STM32F103C8T6",
                "matched_model": "STM32F407VET6",
                "match_type": "RELATED_MODEL",
                "evidence_role": "PROJECT_FACT_EVIDENCE",
                "alias_id": None,
                "supports_project_fact": False,
                "supports_model_parameters": False,
            })

    def test_series_model_cannot_support_model_parameters(self) -> None:
        with self.assertRaisesRegex(ValueError, "Illegal retrieval classification"):
            validate_retrieval_classification({
                "fact_id": "fact-mcu-model",
                "fact_version_id": "fact-mcu-model-v2",
                "locked_model": "STM32F103C8T6",
                "matched_model": "STM32F103ZET6",
                "match_type": "SERIES_MATCH",
                "evidence_role": "MODEL_PARAMETER_EVIDENCE",
                "alias_id": None,
                "supports_project_fact": False,
                "supports_model_parameters": False,
            })

    def test_runtime_rejects_support_flags_for_non_exact_models(self) -> None:
        records = [
            self.valid_record("RELATED_MODEL", "COMPARISON_ONLY", supports_project_fact=True, supports_model_parameters=True),
            self.valid_record("SERIES_MATCH", "GENERAL_PRINCIPLE", supports_project_fact=True, supports_model_parameters=True),
            self.valid_record("CONFLICTING_MODEL", "REJECTED", supports_project_fact=True, supports_model_parameters=True),
        ]
        for record in records:
            with self.assertRaisesRegex(ValueError, "support flags"):
                validate_retrieval_classification(record)

    def test_runtime_validates_confirmed_alias_scope(self) -> None:
        record, aliases, versions = self.approved_alias(
            evidence_role="MODEL_PARAMETER_EVIDENCE",
            alias_scope="PROJECT_FACT_ONLY",
            supports_model_parameters=True,
        )
        with self.assertRaisesRegex(ValueError, "alias_scope"):
            validate_retrieval_classification(record, alias_registry=aliases, fact_versions=versions)

    def test_confirmed_alias_cannot_be_forged_without_an_approved_registry_record(self) -> None:
        record, _, versions = self.approved_alias(matched_model="ESP32")
        with self.assertRaisesRegex(ValueError, "FactAlias registry"):
            validate_retrieval_classification(record, alias_registry=[], fact_versions=versions)

    def test_confirmed_alias_must_belong_to_the_current_fact(self) -> None:
        record, aliases, versions = self.approved_alias()
        aliases[0]["fact_id"] = "fact-wireless-model"
        with self.assertRaisesRegex(ValueError, "current ProjectFactVersion"):
            validate_retrieval_classification(record, alias_registry=aliases, fact_versions=versions)

    def test_confirmed_alias_scope_must_match_the_registry(self) -> None:
        record, aliases, versions = self.approved_alias(alias_scope="PROJECT_FACT_AND_PARAMETERS", evidence_role="MODEL_PARAMETER_EVIDENCE", supports_model_parameters=True)
        with self.assertRaisesRegex(ValueError, "scope does not match"):
            validate_retrieval_classification(record, alias_registry=aliases, fact_versions=versions)

    def test_related_model_cannot_support_project_implementation_claims(self) -> None:
        payload = build_review_payload(FIXTURES)
        confirmed = payload["intake_confirmation"]
        issues = validate_generated_surfaces(confirmed["snapshot"], confirmed["entities"], [{
            "surface": "test_chapter",
            "text": "系统测试对象为 STM32F407VET6，GPIO 与存储参数如下。",
            "context_role": "PROJECT_IMPLEMENTATION",
        }])
        self.assertEqual(issues[0]["issue_code"], "FACT_CONSTRAINT_VIOLATION")
        self.assertEqual(issues[0]["severity"], "BLOCKING")

    def test_locked_model_is_consistent_across_all_required_surfaces(self) -> None:
        payload = build_review_payload(FIXTURES)
        confirmed = payload["intake_confirmation"]
        surfaces = [
            {"surface": name, "text": "项目采用 STM32F103C8T6、DHT11、ESP8266-01S 和 SSD1306。", "context_role": "PROJECT_IMPLEMENTATION"}
            for name in ["outline", "body", "bom", "parameter_table", "figure", "test_chapter", "abstract", "conclusion"]
        ]
        self.assertEqual(validate_generated_surfaces(confirmed["snapshot"], confirmed["entities"], surfaces), [])

    def test_snapshot_builds_a_protected_set_for_every_hardware_and_module_model(self) -> None:
        payload = build_review_payload(FIXTURES)
        confirmed = payload["intake_confirmation"]
        self.assertEqual(protected_models_from_snapshot(confirmed["snapshot"], confirmed["entities"]), {
            "mcu_model": "STM32F103C8T6",
            "sensor_model": "DHT11",
            "wireless_model": "ESP8266-01S",
            "display_driver": "SSD1306",
        })

    def test_module_model_replacements_are_blocking(self) -> None:
        payload = build_review_payload(FIXTURES)
        confirmed = payload["intake_confirmation"]
        replacements = [("DHT11", "DHT22"), ("ESP8266-01S", "ESP32"), ("SSD1306", "SSD1309")]
        for locked, replacement in replacements:
            issues = validate_generated_surfaces(confirmed["snapshot"], confirmed["entities"], [{
                "surface": "body",
                "text": f"项目采用 {replacement}。",
                "context_role": "PROJECT_IMPLEMENTATION",
            }])
            issue = next((item for item in issues if item["locked_model"] == locked), None)
            self.assertIsNotNone(issue, f"{locked} -> {replacement}")
            self.assertEqual(issue["severity"], "BLOCKING")

    def test_cross_series_and_cross_vendor_model_replacements_are_blocking(self) -> None:
        payload = build_review_payload(FIXTURES)
        confirmed = payload["intake_confirmation"]
        replacements = [
            ("DHT11", "SHT31"),
            ("ESP8266-01S", "NRF24L01"),
            ("SSD1306", "SH1106"),
            ("STM32F103C8T6", "ATmega328P"),
        ]
        for locked, replacement in replacements:
            issues = validate_generated_surfaces(confirmed["snapshot"], confirmed["entities"], [{
                "surface": "body",
                "text": f"项目采用 {replacement}。",
                "context_role": "PROJECT_IMPLEMENTATION",
            }])
            issue = next((item for item in issues if item["locked_model"] == locked), None)
            self.assertIsNotNone(issue, f"{locked} -> {replacement}")
            self.assertEqual(issue["severity"], "BLOCKING")

    def test_related_model_is_only_allowed_in_explicit_comparison_context(self) -> None:
        payload = build_review_payload(FIXTURES)
        confirmed = payload["intake_confirmation"]
        issues = validate_generated_surfaces(confirmed["snapshot"], confirmed["entities"], [{
            "surface": "comparison",
            "text": "对比方案采用 STM32F407VET6。",
            "context_role": "COMPARISON_ONLY",
        }])
        self.assertEqual(issues, [])


class ConflictAndVersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = build_review_payload(FIXTURES)

    def test_conflicting_user_materials_create_an_open_conflict_without_auto_selection(self) -> None:
        conflict = self.payload["conflict"]["project_fact_conflict"]
        self.assertEqual(conflict["status"], "OPEN")
        self.assertFalse(conflict["auto_selection_allowed"])
        self.assertEqual({item["canonical_value"] for item in conflict["candidates"]}, {"STM32F103C8T6", "STM32F407VET6"})

    def test_intake_starts_proposed_without_active_snapshot_or_fact_versions(self) -> None:
        initial = self.payload["initial"]
        self.assertIsNone(initial["snapshot"])
        self.assertEqual(initial["entities"]["fact_versions"], [])
        self.assertTrue(all(item["status"] == "PROPOSED" and item["current_fact_version_id"] is None for item in initial["entities"]["facts"]))

    def test_intake_confirmation_creates_versions_snapshot_human_approval_and_audit_event(self) -> None:
        initial = self.payload["initial"]
        confirmed = self.payload["intake_confirmation"]
        self.assertNotEqual(initial["entities"], confirmed["entities"])
        self.assertEqual(confirmed["snapshot"]["status"], "ACTIVE")
        self.assertTrue(confirmed["snapshot"]["snapshot_hash"].startswith("sha256:"))
        self.assertTrue(all(item["status"] == "LOCKED" for item in confirmed["entities"]["facts"]))
        self.assertEqual(confirmed["human_approval"]["approval_type"], "PROJECT_FACT_INTAKE_CONFIRMATION")
        self.assertEqual(confirmed["audit_event"]["event_type"], "PROJECT_FACT_INTAKE_CONFIRMED")

    def test_intake_confirmation_propagates_the_same_actor_to_every_audit_object(self) -> None:
        initial = self.payload["initial"]["entities"]
        confirmed = confirm_intake(initial, approved_by="reviewer-zhang")
        self.assertEqual(confirmed["human_approval"]["approved_by"], "reviewer-zhang")
        self.assertEqual(confirmed["audit_event"]["actor_id"], "reviewer-zhang")
        self.assertTrue(all(item["confirmed_by"] == "reviewer-zhang" for item in confirmed["entities"]["fact_versions"]))
        self.assertEqual(confirmed["snapshot"]["created_by"], "reviewer-zhang")

    def test_conflict_clears_the_current_version_and_suspends_the_current_snapshot(self) -> None:
        conflict = self.payload["conflict"]
        fact = next(item for item in conflict["entities"]["facts"] if item["fact_key"] == "mcu_model")
        self.assertEqual(fact["status"], "CONFLICT")
        self.assertIsNone(fact["current_fact_version_id"])
        self.assertEqual(fact["last_locked_fact_version_id"], "fact-mcu-model-v2")
        self.assertEqual(conflict["snapshot"]["status"], "SUSPENDED")

    def test_every_generated_review_payload_instance_conforms_to_its_schema(self) -> None:
        errors = validate_review_payload_instances(self.payload, ROOT / "schemas")
        self.assertEqual(errors, [])

    def test_dependency_states_follow_the_conflict_transition_table(self) -> None:
        transitions = {item["logical_id"]: item for item in self.payload["conflict"]["transitions"]}
        self.assertEqual(transitions["section_generate_pre_group"]["after"], "INVALIDATED")
        self.assertEqual(transitions["section_generate_ch6"]["after"], "BLOCKED")
        self.assertEqual(transitions["engineering_verify"]["after"], "CANCEL_REQUESTED")
        self.assertEqual(transitions["outline_plan"]["after"], "INVALIDATED")
        self.assertEqual(transitions["background_theory"]["after"], "SUCCEEDED")

    def test_dependency_closure_is_computed_from_edges(self) -> None:
        graph = self.payload["initial"]["dependency_graph"]
        closure = downstream_closure(graph["root"], graph["edges"])
        self.assertIn("nr-ch7-v5", closure)
        broken = [edge for edge in graph["edges"] if edge != ["nr-ch6-v5", "nr-ch7-v5"]]
        self.assertNotIn("nr-ch7-v5", downstream_closure(graph["root"], broken))

    def test_removed_dependency_edge_preserves_the_now_unrelated_target(self) -> None:
        graph = deepcopy(self.payload["initial"]["dependency_graph"])
        graph["edges"] = [edge for edge in graph["edges"] if edge != ["nr-ch6-v5", "nr-ch7-v5"]]
        snapshot = self.payload["intake_confirmation"]["snapshot"]
        targets = dependency_targets(graph["root"], snapshot["snapshot_hash"], graph)
        ch7 = next(item for item in targets if item["logical_id"] == "section_generate_ch7")
        self.assertFalse(ch7["depends_on_fact"])

    def test_claim_artifact_quality_and_delivery_dependencies_are_invalidated(self) -> None:
        invalidated = {(item["target_type"], item["logical_id"]) for item in self.payload["conflict"]["impact"]["invalidated"]}
        self.assertIn(("CLAIM", "claim_mcu_design"), invalidated)
        self.assertIn(("ARTIFACT_VERSION", "retrieval_evidence"), invalidated)
        self.assertIn(("QUALITY_REPORT", "quality_report"), invalidated)
        self.assertIn(("DELIVERY_PACKAGE", "delivery_package"), invalidated)

    def test_confirmation_creates_new_version_snapshot_and_fingerprint(self) -> None:
        initial = self.payload["intake_confirmation"]
        confirmed = self.payload["confirmation"]
        self.assertEqual(confirmed["new_fact_version"]["version"], 3)
        self.assertEqual(confirmed["new_fact_version"]["supersedes_fact_version_id"], "fact-mcu-model-v2")
        self.assertEqual([item["snapshot_id"] for item in confirmed["snapshots"]], ["pfs-task-001-v5", "pfs-task-001-v6"])
        self.assertNotEqual(initial["snapshot"]["snapshot_hash"], confirmed["new_snapshot"]["snapshot_hash"])
        old_outline = next(item for item in initial["targets"] if item["logical_id"] == "outline_plan")
        new_outline = next(item for item in confirmed["targets"] if item["logical_id"] == "outline_plan")
        self.assertNotEqual(old_outline["execution_fingerprint"], new_outline["execution_fingerprint"])

    def test_outline_requires_a_new_node_run_before_another_approval(self) -> None:
        transition = self.payload["confirmation"]["outline_transition"]
        self.assertEqual(transition, {
            "old_node_run_id": "nr-outline-v5",
            "old_state": "INVALIDATED",
            "new_node_run_id": "nr-outline-v6",
            "new_state": "READY",
        })

    def test_active_snapshot_rejects_conflicted_facts(self) -> None:
        entities = build_entities(extract_fixture_set(FIXTURES, conflicting_source=True))
        with self.assertRaisesRegex(ValueError, "unlocked or conflicted"):
            make_snapshot(entities, 6)

    def test_old_versions_and_snapshots_are_retained(self) -> None:
        confirmed = self.payload["confirmation"]
        versions = {item["fact_version_id"]: item for item in confirmed["entities"]["fact_versions"]}
        self.assertIn("fact-mcu-model-v2", versions)
        self.assertEqual(versions["fact-mcu-model-v2"]["status"], "SUPERSEDED")
        self.assertEqual(confirmed["snapshots"][0]["status"], "SUPERSEDED")

    def test_every_retained_fact_version_keeps_resolvable_source_links(self) -> None:
        confirmed = self.payload["confirmation"]["entities"]
        source_link_ids = {item["source_link_id"] for item in confirmed["source_links"]}
        for version in confirmed["fact_versions"]:
            self.assertTrue(set(version["source_link_ids"]).issubset(source_link_ids), version["fact_version_id"])

    def test_ui_payload_is_regenerated_from_the_frozen_fixtures(self) -> None:
        configured = os.environ.get("PROJECT_FACT_UI_PAYLOAD")
        candidates = [Path(configured)] if configured else [
            ROOT.parent / "prototype/project-fact-r4.json",
            ROOT.parent / "uiux-prototype/project-fact-r4.json",
        ]
        payload_path = next((path for path in candidates if path.exists()), None)
        self.assertIsNotNone(payload_path, "missing packaged prototype payload")
        ui_payload = json.loads(payload_path.read_text(encoding="utf-8"))
        self.assertEqual(ui_payload, self.payload)


if __name__ == "__main__":
    unittest.main()
