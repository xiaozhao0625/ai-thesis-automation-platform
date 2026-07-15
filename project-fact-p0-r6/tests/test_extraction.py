from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from project_fact_r6.common import file_hash
from project_fact_r6.extractor import extract_docx, extract_fixture_set, extract_ocr, extract_source_code, find_facts


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


class ExtractionTests(unittest.TestCase):
    def test_frozen_fixture_manifest_matches_every_input(self) -> None:
        manifest = json.loads((FIXTURES / "expected/fixture-manifest.json").read_text(encoding="utf-8"))
        for item in manifest["files"]:
            self.assertEqual(file_hash(FIXTURES / item["path"]), item["sha256"], item["path"])

    def test_same_exact_mcu_is_extracted_from_four_real_source_types(self) -> None:
        observations = extract_fixture_set(FIXTURES)
        mcu = [item for item in observations if item["fact_key"] == "mcu_model"]
        self.assertEqual({item["canonical_value"] for item in mcu}, {"STM32F103C8T6"})
        self.assertEqual({item["source_locator"]["source_type"] for item in mcu}, {"DOCX", "SOURCE_CODE", "SPREADSHEET", "IMAGE_OCR"})
        self.assertTrue(all(item["source_locator"]["artifact_version_id"].startswith("av-") for item in mcu))
        self.assertTrue(all(item["source_locator"]["excerpt_hash"].startswith("sha256:") for item in mcu))

    def test_each_source_type_preserves_a_jumpable_locator(self) -> None:
        observations = extract_fixture_set(FIXTURES)
        by_type = {item["source_locator"]["source_type"]: item["source_locator"] for item in observations if item["fact_key"] == "mcu_model"}
        self.assertEqual(by_type["DOCX"]["paragraph_index"], 2)
        self.assertEqual(by_type["DOCX"]["page_number"], 1)
        self.assertEqual(by_type["SOURCE_CODE"]["symbol_name"], "MCU_MODEL")
        self.assertEqual(by_type["SOURCE_CODE"]["line_start"], 2)
        self.assertEqual(by_type["SPREADSHEET"]["sheet_name"], "硬件清单")
        self.assertEqual(by_type["SPREADSHEET"]["cell_range"], "B7")
        self.assertEqual(by_type["IMAGE_OCR"]["ocr_block_id"], "ocr-block-001")
        self.assertEqual(len(by_type["IMAGE_OCR"]["bbox"]), 4)

    def test_framework_database_parameter_and_modules_are_extracted(self) -> None:
        expected = json.loads((FIXTURES / "expected/project-facts.expected.json").read_text(encoding="utf-8"))
        values = {item["canonical_value"] for item in extract_fixture_set(FIXTURES)}
        self.assertTrue(set(expected["required_values"]).issubset(values))

    def test_generic_task_document_extracts_unseen_model_families_by_slot(self) -> None:
        observations = extract_docx(FIXTURES / "generic/task-document/通用型号任务书.docx", FIXTURES)
        facts = {(item["fact_key"], item["canonical_value"]) for item in observations}
        self.assertTrue({
            ("mcu_model", "RP2040"),
            ("sensor_model", "HDC1080"),
            ("bluetooth_module", "HC-05"),
            ("display_driver", "LCD1602"),
            ("rtc_model", "DS3231"),
        }.issubset(facts))

    def test_slot_semantics_extract_other_vendors_without_brand_patterns(self) -> None:
        facts = {(fact_key, value) for fact_key, _fact_type, value, _start, _end in find_facts(
            "主控采用 GD32F103C8T6，传感器采用 HDC1080，无线模块采用 NRF24L01，显示驱动采用 SH1106。"
        )}
        self.assertEqual(facts, {
            ("mcu_model", "GD32F103C8T6"),
            ("sensor_model", "HDC1080"),
            ("wireless_model", "NRF24L01"),
            ("display_driver", "SH1106"),
        })

    def test_source_config_dict_uses_dynamic_slot_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "devices.py"
            source.write_text(
                '# fixture_commit: generic-001\nDEVICES = {"RTC_MODEL": "DS3231", "MOTOR_DRIVER": "L298N", "RFID_MODULE": "RC522"}\n',
                encoding="utf-8",
            )
            facts = {(item["fact_key"], item["canonical_value"]) for item in extract_source_code(source, source.parent)}
            self.assertEqual(facts, {("rtc_model", "DS3231"), ("motor_driver", "L298N"), ("rfid_module", "RC522")})

    def test_changing_source_input_changes_extracted_fact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            copy = Path(temp_dir) / "config.py"
            shutil.copy2(FIXTURES / "source-code/config.py", copy)
            before = next(item for item in extract_source_code(copy, copy.parent) if item["fact_key"] == "mcu_model")
            copy.write_text(copy.read_text(encoding="utf-8").replace("STM32F103C8T6", "STM32F407VET6"), encoding="utf-8")
            after = next(item for item in extract_source_code(copy, copy.parent) if item["fact_key"] == "mcu_model")
            self.assertEqual(before["canonical_value"], "STM32F103C8T6")
            self.assertEqual(after["canonical_value"], "STM32F407VET6")
            self.assertNotEqual(before["source_locator"]["artifact_version_id"], after["source_locator"]["artifact_version_id"])

    def test_deleting_source_input_is_not_silently_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "config.py"
            with self.assertRaises(FileNotFoundError):
                extract_source_code(missing, missing.parent)

    def test_ocr_requires_the_exact_png_and_text_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            shutil.copy2(FIXTURES / "screenshot/hardware-list.ocr.json", folder / "hardware-list.ocr.json")
            image = bytearray((FIXTURES / "screenshot/hardware-list.png").read_bytes())
            image[-1] ^= 1
            (folder / "hardware-list.png").write_bytes(image)
            with self.assertRaisesRegex(ValueError, "image hash"):
                extract_ocr(folder / "hardware-list.ocr.json", folder)


if __name__ == "__main__":
    unittest.main()
