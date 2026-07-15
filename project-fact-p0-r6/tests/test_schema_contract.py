from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"


def load(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def simple_branch_matches(branch: dict, instance: dict) -> bool:
    if any(key not in instance for key in branch.get("required", [])):
        return False
    for key, rule in branch.get("properties", {}).items():
        if key not in instance:
            continue
        if "const" in rule and instance[key] != rule["const"]:
            return False
        if "enum" in rule and instance[key] not in rule["enum"]:
            return False
    return True


class SchemaContractTests(unittest.TestCase):
    def test_all_schema_files_are_valid_json_and_closed_objects(self) -> None:
        names = {
            "source-locator.schema.json",
            "fact-source-link.schema.json",
            "project-fact.schema.json",
            "project-fact-version.schema.json",
            "project-fact-snapshot.schema.json",
            "project-fact-conflict.schema.json",
            "fact-dependency.schema.json",
            "fact-dependency-graph.schema.json",
            "fact-alias.schema.json",
            "fact-bound-output.schema.json",
            "human-approval.schema.json",
            "audit-event.schema.json",
            "retrieval-request.schema.json",
            "retrieval-classification.schema.json",
        }
        self.assertTrue(names.issubset({path.name for path in SCHEMAS.glob("*.json")}))
        for name in names:
            self.assertFalse(load(name)["additionalProperties"], name)

    def test_locator_requires_source_specific_coordinates(self) -> None:
        schema = load("source-locator.schema.json")
        required_by_type = {
            branch["if"]["properties"]["source_type"]["const"]: set(branch["then"]["required"])
            for branch in schema["allOf"]
        }
        self.assertTrue({"page_number", "paragraph_index", "char_start", "char_end"}.issubset(required_by_type["DOCX"]))
        self.assertTrue({"commit", "line_start", "line_end", "symbol_name"}.issubset(required_by_type["SOURCE_CODE"]))
        self.assertTrue({"sheet_name", "cell_range"}.issubset(required_by_type["SPREADSHEET"]))
        self.assertTrue({"bbox", "ocr_text_hash", "image_sha256"}.issubset(required_by_type["IMAGE_OCR"]))

    def test_related_model_plus_project_fact_evidence_matches_no_schema_branch(self) -> None:
        schema = load("retrieval-classification.schema.json")
        invalid = {
            "match_type": "RELATED_MODEL",
            "evidence_role": "PROJECT_FACT_EVIDENCE",
            "supports_project_fact": False,
            "supports_model_parameters": False,
        }
        matches = [branch for branch in schema["oneOf"] if simple_branch_matches(branch, invalid)]
        self.assertEqual(matches, [])

    def test_retrieval_request_excludes_server_owned_fact_state(self) -> None:
        properties = set(load("retrieval-request.schema.json")["properties"])
        self.assertTrue({
            "locked_model", "fact_version_id", "match_type",
            "supports_project_fact", "supports_model_parameters", "alias_scope",
        }.isdisjoint(properties))

    def test_each_supported_match_type_has_an_explicit_one_of_branch(self) -> None:
        schema = load("retrieval-classification.schema.json")
        branch_types = {branch["properties"]["match_type"]["const"] for branch in schema["oneOf"]}
        self.assertEqual(branch_types, {"EXACT_MODEL", "CONFIRMED_ALIAS", "SERIES_MATCH", "RELATED_MODEL", "CONFLICTING_MODEL"})

    def test_fact_bindings_are_dynamic_structured_entries(self) -> None:
        schema = load("fact-bound-output.schema.json")
        bindings = schema["properties"]["fact_bindings"]
        self.assertIsInstance(bindings["additionalProperties"], dict)
        self.assertEqual(
            set(bindings["additionalProperties"]["required"]),
            {"fact_id", "fact_version_id", "canonical_value"},
        )
        self.assertNotIn("properties", bindings)


if __name__ == "__main__":
    unittest.main()
