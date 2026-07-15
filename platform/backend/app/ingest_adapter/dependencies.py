from __future__ import annotations

from functools import lru_cache

from app.core.config import PLATFORM_ROOT, get_settings
from app.ingest_adapter.paths import ControlledSourceResolver


@lru_cache
def get_source_resolver() -> ControlledSourceResolver:
    settings = get_settings()
    return ControlledSourceResolver(
        platform_root=PLATFORM_ROOT,
        allowed_roots=[settings.benchmark_root],
        artifact_store_root=settings.artifact_store_root,
    )
