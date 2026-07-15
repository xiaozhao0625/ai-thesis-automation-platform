from __future__ import annotations

from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PLATFORM_ROOT = REPOSITORY_ROOT / "platform"


def test_compose_defines_real_postgres_redis_and_three_backend_processes() -> None:
    compose_path = PLATFORM_ROOT / "deploy" / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text("utf-8"))
    services = compose["services"]

    assert set(services) == {"postgres", "redis", "api", "publisher", "worker", "frontend"}
    assert services["postgres"]["image"] == "postgres:17.10-alpine"
    assert services["redis"]["image"] == "redis:7.4.9-alpine"
    assert "alembic upgrade head" in services["api"]["command"]
    assert services["publisher"]["command"] == ["python", "-m", "app.outbox.main"]
    assert services["worker"]["command"] == ["python", "-m", "app.worker.main"]
    assert services["worker"]["depends_on"]["redis"]["condition"] == "service_healthy"


def test_deployment_contract_never_uses_sqlite_or_embedded_redis() -> None:
    deployment_text = "\n".join(
        path.read_text("utf-8")
        for path in (PLATFORM_ROOT / "deploy").rglob("*")
        if path.is_file()
    ).lower()

    assert "sqlite" not in deployment_text
    assert "fakeredis" not in deployment_text
    assert "memory://" not in deployment_text


def test_docker_context_reincludes_the_frozen_noise_fixture() -> None:
    dockerignore = (REPOSITORY_ROOT / ".dockerignore").read_text("utf-8")

    assert "!platform/benchmark/ingest-fixture-v1/**" in dockerignore


def test_environment_and_operator_scripts_are_present() -> None:
    env = (PLATFORM_ROOT / ".env.example").read_text("utf-8")
    assert "DATABASE_URL=" in env
    assert "REDIS_URL=" in env
    assert "ARTIFACT_STORE_ROOT=" in env
    assert "POSTGRES_PASSWORD=" in env
    assert "VITE_API_BASE_URL=\n" in env
    assert "VITE_API_BASE_URL=http://127.0.0.1" not in env

    for name in (
        "dev-up.ps1",
        "dev-down.ps1",
        "test-all.ps1",
        "bootstrap-new-machine.ps1",
        "backup-data.ps1",
        "restore-data.ps1",
        "verify-handoff.ps1",
    ):
        assert (PLATFORM_ROOT / "scripts" / name).is_file(), name


def test_handoff_scripts_capture_counts_and_verify_restored_artifacts() -> None:
    backup = (PLATFORM_ROOT / "scripts" / "backup-data.ps1").read_text("utf-8")
    restore = (PLATFORM_ROOT / "scripts" / "restore-data.ps1").read_text("utf-8")
    verify = (PLATFORM_ROOT / "scripts" / "verify-handoff.ps1").read_text("utf-8")

    assert "app.maintenance.snapshot" in backup
    assert "table_counts" in backup
    assert "artifact_store" in backup
    assert "[System.IO.Compression.ZipFile]::CreateFromDirectory" in backup
    assert "app.maintenance.verify_artifacts" in restore
    assert "table_counts" in restore
    assert "artifact_store" in restore
    assert "format_version" in verify
    assert "table_counts" in verify


def test_docker_only_acceptance_images_cover_backend_frontend_and_e2e() -> None:
    production_compose = yaml.safe_load(
        (PLATFORM_ROOT / "deploy" / "docker-compose.yml").read_text("utf-8")
    )
    assert "healthcheck" in production_compose["services"]["frontend"]

    test_compose_path = PLATFORM_ROOT / "deploy" / "docker-compose.test.yml"
    test_compose = yaml.safe_load(test_compose_path.read_text("utf-8"))
    services = test_compose["services"]

    assert set(services) == {"backend-tests", "frontend-tests", "e2e"}
    assert services["backend-tests"]["build"]["dockerfile"] == (
        "platform/backend/Dockerfile.test"
    )
    assert services["backend-tests"]["environment"]["RUN_REDIS_TESTS"] == "1"
    assert services["frontend-tests"]["build"]["dockerfile"] == "Dockerfile.test"
    assert services["e2e"]["build"]["dockerfile"] == "Dockerfile.e2e"
    assert services["e2e"]["environment"]["RUN_E2E"] == "1"
    assert services["e2e"]["environment"]["E2E_BASE_URL"] == "http://frontend"

    e2e_dockerfile = (PLATFORM_ROOT / "frontend" / "Dockerfile.e2e").read_text(
        "utf-8"
    )
    assert "mcr.microsoft.com/playwright:v1.61.1-noble" in e2e_dockerfile
    test_script = (PLATFORM_ROOT / "scripts" / "test-all.ps1").read_text("utf-8")
    assert "[switch]$Docker" in test_script
    assert "docker-compose.test.yml" in test_script
    assert "thesis_platform_test" in test_script
    assert "cd /app/ingest-cli && python -m pytest -q" in test_script
