from __future__ import annotations

import ast
import json
import re
import struct
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from .common import artifact_version_id, content_hash, file_hash


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

SLOT_DEFINITIONS = {
    "mcu_model": {
        "fact_type": "HARDWARE_MODEL",
        "labels": ["主控芯片", "主控型号", "主控", "单片机", "MCU_MODEL", "MCU"],
    },
    "sensor_model": {
        "fact_type": "MODULE_MODEL",
        "labels": ["温湿度传感器", "温湿度模块", "环境传感器", "传感器型号", "SENSOR_MODEL", "传感器"],
    },
    "wireless_model": {
        "fact_type": "MODULE_MODEL",
        "labels": ["无线通信模块", "无线模块", "通信模块", "WIRELESS_MODEL"],
    },
    "bluetooth_module": {
        "fact_type": "MODULE_MODEL",
        "labels": ["蓝牙模块", "BLUETOOTH_MODULE"],
    },
    "display_driver": {
        "fact_type": "MODULE_MODEL",
        "labels": ["显示驱动芯片", "显示驱动", "驱动芯片", "显示模块", "显示屏", "DISPLAY_DRIVER"],
    },
    "rtc_model": {
        "fact_type": "MODULE_MODEL",
        "labels": ["RTC模块", "RTC型号", "RTC_MODEL", "实时时钟模块"],
    },
    "motor_driver": {
        "fact_type": "MODULE_MODEL",
        "labels": ["电机驱动模块", "电机驱动", "MOTOR_DRIVER"],
    },
    "rfid_module": {
        "fact_type": "MODULE_MODEL",
        "labels": ["RFID模块", "RFID_MODULE"],
    },
    "software_framework": {
        "fact_type": "SOFTWARE_FRAMEWORK",
        "labels": ["服务框架", "软件框架", "WEB_FRAMEWORK", "SOFTWARE_FRAMEWORK"],
    },
    "database_type": {
        "fact_type": "DATABASE_TYPE",
        "labels": ["数据库类型", "数据库", "DATABASE_TYPE"],
    },
    "supply_voltage": {
        "fact_type": "ELECTRICAL_PARAMETER",
        "labels": ["供电电压", "工作电压", "SUPPLY_VOLTAGE"],
    },
}

MODEL_VALUE_PATTERN = r"[A-Za-z][A-Za-z0-9._+\-/]*"
PARAMETER_VALUE_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._+\-/]*"
SLOT_PATTERNS = [
    (
        fact_key,
        definition["fact_type"],
        re.compile(
            rf"(?<![A-Za-z0-9_])(?:{'|'.join(re.escape(label) for label in sorted(definition['labels'], key=len, reverse=True))})"
            rf"(?![A-Za-z0-9_])\s*(?:必须使用|采用|使用|选用|配置为|为|是|[:：=])?\s*"
            rf"(?P<value>{PARAMETER_VALUE_PATTERN if definition['fact_type'] == 'ELECTRICAL_PARAMETER' else MODEL_VALUE_PATTERN})",
            re.I,
        ),
    )
    for fact_key, definition in SLOT_DEFINITIONS.items()
]

SOURCE_SYMBOLS = {
    label.upper(): (fact_key, definition["fact_type"])
    for fact_key, definition in SLOT_DEFINITIONS.items()
    for label in definition["labels"]
    if re.fullmatch(r"[A-Za-z0-9_]+", label)
}


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def find_facts(text: str) -> list[tuple[str, str, str, int, int]]:
    found: list[tuple[str, str, str, int, int]] = []
    seen: set[tuple[str, str, int, int]] = set()
    for fact_key, fact_type, pattern in SLOT_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group("value").strip().rstrip(".,;，。；")
            key = (fact_key, value.casefold(), match.start("value"), match.end("value"))
            if key in seen:
                continue
            seen.add(key)
            found.append((fact_key, fact_type, value, match.start("value"), match.end("value")))
    return sorted(found, key=lambda item: (item[3], item[0]))


def infer_source_symbol(symbol: str) -> tuple[str, str] | None:
    upper = symbol.upper()
    if upper in SOURCE_SYMBOLS:
        return SOURCE_SYMBOLS[upper]
    normalized = re.sub(r"[^A-Z0-9]+", "_", upper).strip("_")
    if normalized in SOURCE_SYMBOLS:
        return SOURCE_SYMBOLS[normalized]
    if normalized.endswith(("_MODEL", "_MODULE", "_DRIVER", "_SENSOR")):
        fact_key = normalized.lower()
        if normalized.startswith(("MCU_", "MAIN_CONTROLLER_", "CONTROLLER_")):
            return "mcu_model", "HARDWARE_MODEL"
        return fact_key, "MODULE_MODEL"
    return None


def observation(
    *,
    fact_key: str,
    fact_type: str,
    canonical_value: str,
    original_value: str,
    confidence: float,
    locator: dict[str, Any],
) -> dict[str, Any]:
    source_link_id = "fsl-" + content_hash({"value": canonical_value, "locator": locator})[7:23]
    return {
        "observation_id": "obs-" + source_link_id[4:],
        "fact_key": fact_key,
        "fact_type": fact_type,
        "canonical_value": canonical_value,
        "original_value": original_value,
        "confidence": confidence,
        "source_link_id": source_link_id,
        "source_locator": locator,
    }


def base_locator(path: Path, root: Path, source_type: str, excerpt: str) -> dict[str, Any]:
    return {
        "artifact_version_id": artifact_version_id(path),
        "source_type": source_type,
        "file_path": relative_path(path, root),
        "excerpt": excerpt,
        "excerpt_hash": content_hash(excerpt.encode("utf-8")),
    }


def extract_docx(path: Path, root: Path) -> list[dict[str, Any]]:
    with ZipFile(path) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    results: list[dict[str, Any]] = []
    section = ""
    page_number = 1
    paragraphs = document.findall(f".//{{{WORD_NS}}}p")
    for paragraph_index, paragraph in enumerate(paragraphs, start=1):
        text = "".join(node.text or "" for node in paragraph.findall(f".//{{{WORD_NS}}}t"))
        if not text:
            continue
        style = paragraph.find(f"./{{{WORD_NS}}}pPr/{{{WORD_NS}}}pStyle")
        if style is not None and style.attrib.get(f"{{{WORD_NS}}}val", "").startswith("Heading"):
            section = text
        for fact_key, fact_type, value, start, end in find_facts(text):
            locator = base_locator(path, root, "DOCX", text)
            locator.update({
                "page_number": page_number,
                "section": section,
                "paragraph_index": paragraph_index,
                "char_start": start,
                "char_end": end,
            })
            results.append(observation(
                fact_key=fact_key,
                fact_type=fact_type,
                canonical_value=value,
                original_value=text,
                confidence=1.0,
                locator=locator,
            ))
        rendered_breaks = paragraph.findall(f".//{{{WORD_NS}}}lastRenderedPageBreak")
        explicit_breaks = [node for node in paragraph.findall(f".//{{{WORD_NS}}}br") if node.attrib.get(f"{{{WORD_NS}}}type") == "page"]
        page_number += len(rendered_breaks) + len(explicit_breaks)
    return results


def extract_source_code(path: Path, root: Path) -> list[dict[str, Any]]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    commit_match = re.search(r"fixture_commit:\s*([^\s]+)", source)
    commit = commit_match.group(1) if commit_match else "UNKNOWN"
    tree = ast.parse(source, filename=str(path))
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()

    def append_result(fact_key: str, fact_type: str, canonical_value: str, line_number: int, symbol_name: str) -> None:
        key = (fact_key, canonical_value.casefold(), line_number)
        if key in seen:
            return
        seen.add(key)
        excerpt = lines[line_number - 1]
        locator = base_locator(path, root, "SOURCE_CODE", excerpt)
        locator.update({
            "commit": commit,
            "line_start": line_number,
            "line_end": line_number,
            "symbol_name": symbol_name,
        })
        results.append(observation(
            fact_key=fact_key,
            fact_type=fact_type,
            canonical_value=canonical_value,
            original_value=excerpt,
            confidence=1.0,
            locator=locator,
        ))

    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        target = node.targets[0] if isinstance(node, ast.Assign) else node.target
        value_node = node.value
        if not isinstance(target, ast.Name):
            continue
        inferred = infer_source_symbol(target.id)
        if inferred and isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
            append_result(*inferred, value_node.value.strip(), node.lineno, target.id)
        if isinstance(value_node, ast.Dict):
            for key_node, item_node in zip(value_node.keys, value_node.values):
                if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                    continue
                if not isinstance(item_node, ast.Constant) or not isinstance(item_node.value, str):
                    continue
                item_fact = infer_source_symbol(key_node.value)
                if item_fact:
                    append_result(*item_fact, item_node.value.strip(), getattr(item_node, "lineno", node.lineno), key_node.value)

    for line_number, line in enumerate(lines, start=1):
        for fact_key, fact_type, value, _start, _end in find_facts(line):
            append_result(fact_key, fact_type, value, line_number, fact_key)
    return results


def cell_text(cell: ET.Element) -> str:
    if cell.attrib.get("t") == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(f".//{{{SHEET_NS}}}t"))
    value = cell.find(f"{{{SHEET_NS}}}v")
    return value.text if value is not None and value.text else ""


def extract_spreadsheet(path: Path, root: Path) -> list[dict[str, Any]]:
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet = workbook.find(f".//{{{SHEET_NS}}}sheet")
        sheet_name = sheet.attrib["name"] if sheet is not None else "Sheet1"
        worksheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    results: list[dict[str, Any]] = []
    for row in worksheet.findall(f".//{{{SHEET_NS}}}row"):
        cells = {cell.attrib["r"]: cell_text(cell) for cell in row.findall(f"{{{SHEET_NS}}}c")}
        row_number = row.attrib["r"]
        label = cells.get(f"A{row_number}", "")
        for cell_ref, value_text in cells.items():
            if not value_text or cell_ref.startswith("A"):
                continue
            excerpt = f"{label}：{value_text}" if label else value_text
            for fact_key, fact_type, value, _start, _end in find_facts(excerpt):
                locator = base_locator(path, root, "SPREADSHEET", excerpt)
                locator.update({"sheet_name": sheet_name, "cell_range": cell_ref})
                results.append(observation(
                    fact_key=fact_key,
                    fact_type=fact_type,
                    canonical_value=value,
                    original_value=excerpt,
                    confidence=1.0,
                    locator=locator,
                ))
    return results


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError(f"Not a PNG fixture: {path}")
    return struct.unpack(">II", data[16:24])


def extract_ocr(path: Path, root: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    image_path = path.parent / payload["image_file"]
    if payload["image_sha256"] != file_hash(image_path):
        raise ValueError("Frozen OCR image hash does not match the PNG")
    width, height = png_dimensions(image_path)
    results: list[dict[str, Any]] = []
    for block in payload["blocks"]:
        text = block["text"]
        if block["text_hash"] != content_hash(text.encode("utf-8")):
            raise ValueError(f"OCR text hash mismatch: {block['block_id']}")
        x1, y1, x2, y2 = block["bbox"]
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise ValueError(f"OCR bbox outside image: {block['block_id']}")
        for fact_key, fact_type, value, _start, _end in find_facts(text):
            locator = base_locator(image_path, root, "IMAGE_OCR", text)
            locator.update({
                "page_index": payload["page_index"],
                "bbox": block["bbox"],
                "ocr_block_id": block["block_id"],
                "ocr_text": text,
                "ocr_text_hash": block["text_hash"],
                "image_sha256": payload["image_sha256"],
            })
            results.append(observation(
                fact_key=fact_key,
                fact_type=fact_type,
                canonical_value=value,
                original_value=text,
                confidence=float(block["confidence"]),
                locator=locator,
            ))
    return results


def extract_fixture_set(fixtures: Path, *, conflicting_source: bool = False) -> list[dict[str, Any]]:
    source_path = fixtures / ("conflicts/source-code/config.py" if conflicting_source else "source-code/config.py")
    extractors: Iterable[tuple[Path, Any]] = [
        (fixtures / "task-document/任务书.docx", extract_docx),
        (source_path, extract_source_code),
        (fixtures / "spreadsheet/BOM.xlsx", extract_spreadsheet),
        (fixtures / "screenshot/hardware-list.ocr.json", extract_ocr),
    ]
    observations: list[dict[str, Any]] = []
    for path, extractor in extractors:
        observations.extend(extractor(path, fixtures))
    return sorted(observations, key=lambda item: (item["fact_key"], item["source_locator"]["source_type"], item["source_link_id"]))
