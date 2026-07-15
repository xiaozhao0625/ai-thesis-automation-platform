from __future__ import annotations

import unittest
from pathlib import Path
import json
from copy import deepcopy

from project_fact_r2.governance import (
    build_entities,
    build_review_payload,
    classify_model,
    dependency_targets,
    downstream_closure,
    make_snapshot,
    validate_generated_surfaces,
    validate_retrieval_classification,
)
from project_fact_r2.extractor import extract_fixture_set


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


class RetrievalConstraintTests(unittest.TestCase):
    def test_exact_series_and_related_models_are_distinct(self) -> None:
        self.assertEqual(classify_model("STM32F103C8T6", "STM32F103C8T6"), "EXACT_MODEL")
        self.assertEqual(classify_model("STM32F103C8T6", "STM32F103ZET6"), "SERIES_MATCH")
        self.assertEqual(classify_model("STM32F103C8T6", "STM32F407VET6"), "RELATED_MODEL")

    def test_related_model_cannot_be_project_fact_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "Illegal retrieval classification"):
            validate_retrieval_classification({
                "match_type": "RELATED_MODEL",
                "evidence_role": "PROJECT_FACT_EVIDENCE",
            })

    def test_series_model_cannot_support_model_parameters(self) -> None:
        with self.assertRaisesRegex(ValueError, "Illegal retrieval classification"):
            validate_retrieval_classification({
                "match_type": "SERIES_MATCH",
                "evidence_role": "MODEL_PARAMETER_EVIDENCE",
            })

    def test_related_model_cannot_support_project_implementation_claims(self) -> None:
        issues = validate_generated_surfaces("STM32F103C8T6", [{
            "surface": "test_chapter",
            "text": "系统测试对象为 STM32F407VET6，GPIO 与存储参数如下。",
            "context_role": "PROJECT_IMPLEMENTATION",
        }])
        self.assertEqual(issues[0]["issue_code"], "FACT_CONSTRAINT_VIOLATION")
        self.assertEqual(issues[0]["severity"], "BLOCKING")

    def test_locked_model_is_consistent_across_all_required_surfaces(self) -> None:
        surfaces = [
            {"surface": name, "text": "项目采用 STM32F103C8T6。", "context_role": "PROJECT_IMPLEMENTATION"}
            for name in ["outline", "body", "bom", "parameter_table", "figure", "test_chapter", "abstract", "conclusion"]
        ]
        self.assertEqual(validate_generated_surfaces("STM32F103C8T6", surfaces), [])

    def test_related_model_is_only_allowed_in_explicit_comparison_context(self) -> None:
        issues = validate_generated_surfaces("STM32F103C8T6", [{
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
        snapshot = self.payload["initial"]["snapshot"]
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
        initial = self.payload["initial"]
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
        ui_payload = json.loads((ROOT.parent / "uiux-prototype/project-fact-r2.json").read_text(encoding="utf-8"))
        self.assertEqual(ui_payload, self.payload)


if __name__ == "__main__":
    unittest.main()
