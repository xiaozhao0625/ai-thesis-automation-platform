from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PLATFORM_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Spectrum Ledger"
    environment: str = "development"
    database_url: str = (
        "postgresql+psycopg://thesis:thesis@127.0.0.1:5432/thesis_platform"
    )
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_stream: str = "thesis:node-jobs:v1"
    redis_consumer_group: str = "material-workers:v1"
    artifact_store_root: Path = Field(
        default_factory=lambda: PLATFORM_ROOT / "artifact_store"
    )
    benchmark_root: Path = Field(
        default_factory=lambda: PLATFORM_ROOT / "benchmark"
    )
    ingest_work_root: Path = Field(
        default_factory=lambda: PLATFORM_ROOT / ".runtime" / "ingest-work"
    )
    ingest_cli_src: Path = Field(
        default_factory=lambda: PLATFORM_ROOT.parent / "ingest-cli" / "src"
    )
    lease_ttl_seconds: int = 60
    heartbeat_interval_seconds: int = 15
    worker_poll_milliseconds: int = 1000
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
