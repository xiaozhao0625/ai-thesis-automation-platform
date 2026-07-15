from __future__ import annotations

import hashlib
from pathlib import Path


FIXTURE_FILE_COUNT = 128
FIXTURE_LICENSE = "CC0-1.0 synthetic test data"


def fixture_files() -> dict[str, bytes]:
    files: dict[str, bytes] = {
        "project/docs/任务书.docx": b"synthetic requirement document",
        "project/docs/项目说明.docx": b"synthetic project description",
        "project/docs/论文终稿.docx": b"synthetic current thesis " * 40,
        "project/docs/论文终稿2.docx": b"synthetic alternate thesis " * 40,
        "project/docs/论文最终版.pdf": b"%PDF synthetic thesis candidate",
        "project/docs/学校模板.docx": b"synthetic school template",
        "project/docs/自动生成草稿.docx": b"synthetic generated draft",
        "project/historical/旧论文终稿.docx": b"synthetic historical paper",
        "project/src/main.py": b"print('synthetic main')\n",
        "project/src/app.py": b"print('synthetic app')\n",
        "project/src/models.py": b"class SyntheticModel: pass\n",
        "project/src/views.py": b"def synthetic_view(): return {}\n",
        "project/src/utils.py": b"def synthetic_util(): return 1\n",
        "project/src/service.py": b"class SyntheticService: pass\n",
        "project/src/repository.py": b"class SyntheticRepository: pass\n",
        "project/src/api.py": b"def synthetic_api(): return 'ok'\n",
        "project/src/auth.py": b"def synthetic_auth(): return False\n",
        "project/src/cli.py": b"def synthetic_cli(): return 0\n",
        "project/frontend/main.js": b"console.log('synthetic');\n",
        "project/frontend/app.vue": b"<template><main>Synthetic</main></template>\n",
        "project/native/main.c": b"int main(void) { return 0; }\n",
        "project/native/main.h": b"int main(void);\n",
        "project/go/main.go": b"package main\nfunc main() {}\n",
        "project/tests/test_main.py": b"def test_main(): assert True\n",
        "project/tests/test_api.py": b"def test_api(): assert True\n",
        "project/tests/test_models.py": b"def test_models(): assert True\n",
        "project/tests/test_service.py": b"def test_service(): assert True\n",
        "project/tests/test_ui.js": b"console.log('synthetic test');\n",
        "project/tests/fixtures.json": b'{"synthetic":true}\n',
        "project/migrations/001_create.sql": b"CREATE TABLE sample(id INT);\n",
        "project/migrations/002_index.sql": b"CREATE INDEX sample_idx ON sample(id);\n",
        "project/migrations/003_seed.sql": b"INSERT INTO sample VALUES (1);\n",
        "project/migrations/README.md": b"Synthetic migrations only.\n",
        "project/pyproject.toml": b"[project]\nname='synthetic-fixture'\n",
        "project/requirements.txt": b"pytest==9.0.3\n",
        "project/README.md": b"# Synthetic controlled fixture\n",
        "project/config/settings.yaml": b"mode: synthetic\n",
        "project/config/app.ini": b"[app]\nmode=synthetic\n",
        "project/screenshots/student-face-01.jpg": b"synthetic face-image placeholder",
        "project/screenshots/dashboard.png": b"synthetic dashboard placeholder",
        "project/screenshots/chart.png": b"synthetic chart placeholder",
        "project/screenshots/flow.svg": b"<svg><title>Synthetic</title></svg>",
        "project/screenshots/device.webp": b"synthetic device placeholder",
        "project/screenshots/result.tiff": b"synthetic result placeholder",
        "project/tables/results.csv": b"case,value\nsynthetic,1\n",
        "project/tables/measurements.tsv": b"case\tvalue\nsynthetic\t1\n",
        "project/tables/source.xlsx": b"synthetic spreadsheet placeholder",
        "project/fixed-official-sources/standard-01.pdf": b"%PDF synthetic public snapshot 01",
        "project/fixed-official-sources/standard-02.pdf": b"%PDF synthetic public snapshot 02",
        "project/fixed-official-sources/datasheet-01.pdf": b"%PDF synthetic public datasheet 01",
        "project/fixed-official-sources/datasheet-02.pdf": b"%PDF synthetic public datasheet 02",
        "project/fixed-official-sources/api-reference.html": b"<html>Synthetic public reference</html>",
        "project/references/参考文献线索.txt": (
            "Smith J. Synthetic Reference. 2024. doi:10.1234/synthetic\n"
        ).encode("utf-8"),
        "project/references/bare-clues.txt": b"unstructured synthetic clue only\n",
        "project/.venv/Lib/site.py": b"synthetic dependency",
        "project/.venv/Lib/package.py": b"synthetic dependency",
        "project/.venv/Scripts/activate.bat": b"synthetic inert dependency",
        "project/.venv/pyvenv.cfg": b"synthetic dependency",
        "project/.venv/cache/item.bin": b"synthetic dependency",
        "project/node_modules/pkg/index.js": b"synthetic dependency",
        "project/node_modules/pkg/package.json": b'{"synthetic":true}',
        "project/node_modules/pkg/README.md": b"synthetic dependency",
        "project/node_modules/other/index.js": b"synthetic dependency",
        "project/node_modules/other/license.txt": b"synthetic dependency",
        "project/vendor/pkg/source.py": b"synthetic vendor dependency",
        "project/vendor/pkg/data.pdf": b"%PDF synthetic vendor dependency",
        "project/vendor/pkg/LICENSE": b"synthetic license",
        "project/vendor/pkg/config.json": b'{"synthetic":true}',
        "project/build/app.js": b"synthetic build output",
        "project/build/app.css": b"synthetic build output",
        "project/dist/bundle.js": b"synthetic build output",
        "project/dist/index.html": b"synthetic build output",
        "project/backups/论文终稿.docx.bak": b"synthetic backup",
        "project/backups/main.py~": b"synthetic backup",
        "project/backups/~$论文终稿.docx": b"synthetic autosave",
        "project/backups/settings.old": b"synthetic backup",
        "project/backups/report.autosave": b"synthetic autosave",
        "project/quarantine/run.exe": b"MZ SYNTHETIC INERT FIXTURE - NOT EXECUTABLE",
        "project/quarantine/lib.dll": b"MZ SYNTHETIC INERT FIXTURE - NOT EXECUTABLE",
        "project/quarantine/setup.bat": b"REM SYNTHETIC INERT FIXTURE\n",
        "project/quarantine/run.cmd": b"REM SYNTHETIC INERT FIXTURE\n",
        "project/quarantine/script.ps1": b"# SYNTHETIC INERT FIXTURE\n",
        "project/quarantine/tool.jar": b"SYNTHETIC INERT FIXTURE",
        "project/quarantine/package.msi": b"SYNTHETIC INERT FIXTURE",
        "project/quarantine/blob.xyz": b"\x00SYNTHETIC INERT BINARY FIXTURE",
        "project/database/prod.dump": b"synthetic database dump",
        "project/database/users.sqlite3": b"synthetic database placeholder",
        "project/database/export.sql": b"-- synthetic dump export\n",
        "project/database/snapshot.dmp": b"synthetic database snapshot",
        "project/credentials/.env": b"SYNTHETIC_TOKEN=not-a-real-secret\n",
        "project/credentials/secrets.json": b'{"synthetic":"not-real"}\n',
        "project/credentials/id_rsa": b"SYNTHETIC NOT A REAL PRIVATE KEY\n",
        "project/credentials/password.txt": b"synthetic-not-a-password\n",
        "project/archives/materials.zip": b"SYNTHETIC INERT ARCHIVE PLACEHOLDER",
        "project/archives/materials.rar": b"SYNTHETIC INERT ARCHIVE PLACEHOLDER",
        "project/archives/materials.7z": b"SYNTHETIC INERT ARCHIVE PLACEHOLDER",
        "project/archives/materials.tgz": b"SYNTHETIC INERT ARCHIVE PLACEHOLDER",
        "project/media/interview-01.mp3": b"synthetic interview audio placeholder",
        "project/media/demo.mp4": b"synthetic video placeholder",
        "project/media/note.wav": b"synthetic audio placeholder",
        "project/media/demo.webm": b"synthetic video placeholder",
        "project/sensitive/调查问卷.csv": "问题,回答\n合成问题,合成回答\n".encode("utf-8"),
        "project/sensitive/访谈记录.txt": "仅含合成访谈内容。\n".encode("utf-8"),
        "project/sensitive/respondent.txt": b"synthetic.user@example.com 13800138000\n",
        "project/sensitive/人脸照片.png": b"synthetic face-image placeholder",
        "project/duplicates/main-copy-01.py": b"print('synthetic main')\n",
        "project/duplicates/main-copy-02.py": b"print('synthetic main')\n",
        "project/duplicates/readme-copy.md": b"# Synthetic controlled fixture\n",
        "project/duplicates/result-copy.csv": b"case,value\nsynthetic,1\n",
    }
    filler_index = 1
    while len(files) < FIXTURE_FILE_COUNT:
        relative_path = f"project/notes/synthetic-note-{filler_index:03d}.txt"
        files[relative_path] = (
            f"Synthetic fixture note {filler_index:03d}; no real research data.\n"
        ).encode("utf-8")
        filler_index += 1
    if len(files) != FIXTURE_FILE_COUNT:
        raise AssertionError(f"fixture contains {len(files)} files")
    return files


def build_controlled_sample(root: Path) -> dict[str, str]:
    inventory: dict[str, str] = {}
    for relative_path, payload in fixture_files().items():
        destination = root / Path(*relative_path.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        inventory[relative_path] = hashlib.sha256(payload).hexdigest()
    return inventory


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    generated = build_controlled_sample(args.output)
    print(f"generated {len(generated)} synthetic files in {args.output.resolve()}")
