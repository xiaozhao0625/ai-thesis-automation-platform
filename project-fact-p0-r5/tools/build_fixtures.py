from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
FIXED_ZIP_TIME = (2026, 7, 15, 0, 0, 0)


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_zip(path: Path, entries: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w") as archive:
        for name in sorted(entries):
            info = ZipInfo(name, FIXED_ZIP_TIME)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, entries[name].encode("utf-8"))


def build_docx(path: Path) -> None:
    document = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>硬件选型</w:t></w:r></w:p>
    <w:p><w:r><w:t>项目约束：主控必须使用 STM32F103C8T6；温湿度模块采用 DHT11；无线模块采用 ESP8266-01S；显示屏为 0.96 英寸 OLED，驱动芯片 SSD1306；供电电压为 3.3V。</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>软件环境</w:t></w:r></w:p>
    <w:p><w:r><w:t>服务框架采用 FastAPI，数据库采用 PostgreSQL。</w:t></w:r></w:p>
    <w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>
  </w:body>
</w:document>"""
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    write_zip(path, {
        "[Content_Types].xml": content_types,
        "_rels/.rels": rels,
        "word/document.xml": document,
    })


def xml_cell(ref: str, value: str) -> str:
    return f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'


def build_xlsx(path: Path) -> None:
    rows = {
        1: [("A1", "项目"), ("B1", "型号或参数")],
        2: [("A2", "温湿度模块"), ("B2", "DHT11")],
        3: [("A3", "无线模块"), ("B3", "ESP8266-01S")],
        4: [("A4", "显示屏"), ("B4", "0.96 英寸 OLED / SSD1306")],
        5: [("A5", "数据库"), ("B5", "PostgreSQL")],
        6: [("A6", "供电电压"), ("B6", "3.3V")],
        7: [("A7", "主控芯片"), ("B7", "STM32F103C8T6")],
    }
    sheet_rows = "".join(
        f'<row r="{number}">{"".join(xml_cell(ref, value) for ref, value in cells)}</row>'
        for number, cells in rows.items()
    )
    sheet = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>{sheet_rows}</sheetData>
</worksheet>"""
    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="硬件清单" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""
    package_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""
    write_zip(path, {
        "[Content_Types].xml": content_types,
        "_rels/.rels": package_rels,
        "xl/_rels/workbook.xml.rels": workbook_rels,
        "xl/workbook.xml": workbook,
        "xl/worksheets/sheet1.xml": sheet,
    })


FONT = {
    " ": ["00000"] * 7,
    ":": ["00000", "00100", "00100", "00000", "00100", "00100", "00000"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
}


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def build_png(path: Path, text: str) -> list[int]:
    width, height, scale = 620, 80, 5
    pixels = bytearray([255] * width * height * 3)
    x0, y0 = 20, 20
    for index, char in enumerate(text):
        glyph = FONT[char]
        gx = x0 + index * 6 * scale
        for row, bits in enumerate(glyph):
            for column, bit in enumerate(bits):
                if bit != "1":
                    continue
                for dy in range(scale):
                    for dx in range(scale):
                        x, y = gx + column * scale + dx, y0 + row * scale + dy
                        offset = (y * width + x) * 3
                        pixels[offset:offset + 3] = b"\x10\x20\x30"
    scanlines = b"".join(b"\x00" + pixels[row * width * 3:(row + 1) * width * 3] for row in range(height))
    png = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += png_chunk(b"IDAT", zlib.compress(scanlines, 9))
    png += png_chunk(b"IEND", b"")
    path.write_bytes(png)
    return [x0, y0, x0 + len(text) * 6 * scale - scale, y0 + 7 * scale]


def main() -> None:
    docx = FIXTURES / "task-document" / "任务书.docx"
    xlsx = FIXTURES / "spreadsheet" / "BOM.xlsx"
    image = FIXTURES / "screenshot" / "hardware-list.png"
    ocr = FIXTURES / "screenshot" / "hardware-list.ocr.json"
    build_docx(docx)
    build_xlsx(xlsx)
    ocr_text = "MCU: STM32F103C8T6"
    bbox = build_png(image, ocr_text)
    ocr_payload = {
        "ocr_version": "frozen-ocr-v1",
        "image_file": "hardware-list.png",
        "image_sha256": sha256_file(image),
        "page_index": 0,
        "blocks": [{
            "block_id": "ocr-block-001",
            "bbox": bbox,
            "text": ocr_text,
            "text_hash": sha256_bytes(ocr_text.encode("utf-8")),
            "confidence": 0.99,
        }],
    }
    ocr.write_text(json.dumps(ocr_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    inputs = [
        docx,
        FIXTURES / "source-code" / "config.py",
        xlsx,
        image,
        ocr,
        FIXTURES / "conflicts" / "source-code" / "config.py",
        FIXTURES / "expected" / "dependency-graph.json",
    ]
    manifest = {
        "fixture_version": "v0.3.2-P0-r5",
        "files": [
            {
                "path": path.relative_to(FIXTURES).as_posix(),
                "sha256": sha256_file(path),
                "artifact_version_id": "av-" + hashlib.sha256(path.read_bytes()).hexdigest()[:16],
            }
            for path in inputs
        ],
    }
    expected = {
        "mcu_model": "STM32F103C8T6",
        "mcu_source_types": ["DOCX", "SOURCE_CODE", "SPREADSHEET", "IMAGE_OCR"],
        "required_values": ["STM32F103C8T6", "DHT11", "ESP8266-01S", "SSD1306", "FastAPI", "PostgreSQL", "3.3V"],
        "conflicting_mcu_model": "STM32F407VET6",
    }
    expected_dir = FIXTURES / "expected"
    expected_dir.mkdir(parents=True, exist_ok=True)
    (expected_dir / "fixture-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (expected_dir / "project-facts.expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
