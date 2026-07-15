from __future__ import annotations

from functools import lru_cache

from app.artifacts.store import LocalArtifactStore
from app.core.config import get_settings


@lru_cache
def get_artifact_store() -> LocalArtifactStore:
    return LocalArtifactStore(get_settings().artifact_store_root)
