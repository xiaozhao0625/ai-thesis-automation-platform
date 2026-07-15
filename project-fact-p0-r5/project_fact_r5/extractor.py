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

FACT_PATTERNS = [
    ("mcu_model", "HARDWARE_MODEL", re.compile(r"\bSTM32[A-Z0-9-]+\b", re.I), str.upper),
    ("sensor_model", "MODULE_MODEL", re.compile(r"\bDHT\d{2}\b", re.I), str.upper),
    ("wireless_model", "MODULE_MODEL", re.compile(r"\bESP8266-01S\b", re.I), str.upper),
    ("display_driver", "MODULE_MODEL", re.compile(r"\bSSD1306\b", re.I), str.upper),
    ("software_framework", "SOFTWARE_FRAMEWORK", re.compile(r"\bFastAPI\b", re.I), lambda _: "FastAPI"),
    ("database_type", "DATABASE_TYPE", re.compile(r"\bPostgreSQL\b", re.I), lambda _: "PostgreSQL"),
    ("supply_voltage", "ELECTRICAL_PARAMETER", re.compile(r"\b\d+(?:\.\d+)?V\b", re.I), str.upper),
]

SOURCE_SYMBOLS = {
    "MCU_MODEL": ("mcu_model", "HARDWARE_MODEL"),
    "SENSOR_MODEL": ("sensor_model", "MODULE_MODEL"),
    "WIRELESS_MODEL": ("wireless_model", "MODULE_MODEL"),
    "DISPLAY_DRIVER": ("display_driver", "MODULE_MODEL"),
    "WEB_FRAMEWORK": ("software_framework", "SOFTWARE_FRAMEWORK"),
    "DATABASE_TYPE": ("database_type", "DATABASE_TYPE"),
    "SUPPLY_VOLTAGE": ("supply_voltage", "ELECTRICAL_PARAMETER"),
}


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def find_facts(text: str) -> list[tuple[str, str, str, int, int]]:
    found: list[tuple[str, str, str, int, int]] = []
    for fact_key, fact_type, pattern, normalize in FACT_PATTERNS:
        for match in pattern.finditer(text):
            found.append((fact_key, fact_type, normalize(match.group(0)), match.start(), match.end()))
    return sorted(found, key=lambda item: (item[3], item[0]))


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
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        target = node.targets[0] if isinstance(node, ast.Assign) else node.target
        value_node = node.value
        if not isinstance(target, ast.Name) or target.id not in SOURCE_SYMBOLS:
            continue
        if not isinstance(value_node, ast.Constant) or not isinstance(value_node.value, str):
            continue
        fact_key, fact_type = SOURCE_SYMBOLS[target.id]
        canonical_value = value_node.value.strip()
        if fact_type in {"HARDWARE_MODEL", "MODULE_MODEL", "ELECTRICAL_PARAMETER"}:
            canonical_value = canonical_value.upper()
        excerpt = lines[node.lineno - 1]
        locator = base_locator(path, root, "SOURCE_CODE", excerpt)
        locator.update({
            "commit": commit,
            "line_start": node.lineno,
            "line_end": getattr(node, "end_lineno", node.lineno),
            "symbol_name": target.id,
        })
        results.append(observation(
            fact_key=fact_key,
            fact_type=fact_type,
            canonical_value=canonical_value,
            original_value=excerpt,
            confidence=1.0,
            locator=locator,
        ))
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
            for fact_key, fact_type, value, _start, _end in find_facts(value_text):
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
