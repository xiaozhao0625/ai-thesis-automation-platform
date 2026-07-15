from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def content_hash(value: Any) -> str:
    data = value if isinstance(value, bytes) else canonical_json(value)
    return "sha256:" + hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str:
    return content_hash(path.read_bytes())


def artifact_version_id(path: Path) -> str:
    return "av-" + hashlib.sha256(path.read_bytes()).hexdigest()[:16]
