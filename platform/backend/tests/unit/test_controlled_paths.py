from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import ValidationFailure
from app.ingest_adapter.paths import ControlledSourceResolver


def resolver(tmp_path: Path) -> ControlledSourceResolver:
    platform = tmp_path / "platform"
    benchmark = platform / "benchmark"
    benchmark.mkdir(parents=True, exist_ok=True)
    return ControlledSourceResolver(
        platform_root=platform,
        allowed_roots=[benchmark],
        artifact_store_root=platform / "artifact_store",
    )


def test_relative_benchmark_path_resolves_inside_allowed_root(tmp_path: Path) -> None:
    source = tmp_path / "platform" / "benchmark" / "ingest-fixture-v1"
    source.mkdir(parents=True)

    resolved = resolver(tmp_path).resolve("benchmark/ingest-fixture-v1")

    assert resolved == source.resolve()


@pytest.mark.parametrize(
    "value",
    ["C:/Windows", "../outside", "benchmark/../../outside", "//server/share"],
)
def test_absolute_or_traversing_source_path_is_rejected(
    tmp_path: Path, value: str
) -> None:
    with pytest.raises(ValidationFailure) as raised:
        resolver(tmp_path).resolve(value)

    assert raised.value.code == "SOURCE_PATH_NOT_ALLOWED"


def test_artifact_store_cannot_be_selected_as_source(tmp_path: Path) -> None:
    path = tmp_path / "platform" / "artifact_store" / "run"
    path.mkdir(parents=True)

    with pytest.raises(ValidationFailure):
        resolver(tmp_path).resolve("artifact_store/run")


def test_missing_source_has_distinct_error_code(tmp_path: Path) -> None:
    with pytest.raises(ValidationFailure) as raised:
        resolver(tmp_path).resolve("benchmark/missing")

    assert raised.value.code == "SOURCE_PATH_NOT_FOUND"
