from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app.artifacts.dependencies import get_artifact_store
from app.artifacts.store import LocalArtifactStore
from app.db.models import ArtifactVersion
from app.db.session import get_session
from app.main import create_app
from tests.integration.test_material_ingest_job import handler, queued_job


@pytest.mark.postgres
@pytest.mark.integration
def test_ingest_summary_artifact_list_and_verified_download(
    db_session, tmp_path: Path
) -> None:
    created, node = queued_job(db_session)
    worker = handler(db_session, tmp_path)
    worker.handle(
        {
            "node_run_id": str(node.id),
            "execution_fingerprint": node.execution_fingerprint,
        }
    )
    store = LocalArtifactStore(tmp_path / "artifacts")
    app = create_app()

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_artifact_store] = lambda: store
    client = TestClient(app)

    summary = client.get(f"/api/tasks/{created.task.id}/ingest/summary")
    assert summary.status_code == 200
    assert summary.json()["total_files"] == 128
    assert summary.json()["manifest_status"] == "COMPLETED"

    artifacts = client.get(f"/api/tasks/{created.task.id}/ingest/artifacts")
    assert artifacts.status_code == 200
    assert artifacts.json()["total"] == 10
    manifest_item = next(
        item
        for item in artifacts.json()["items"]
        if item["output_role"] == "INGEST_MANIFEST"
    )
    version = db_session.get(ArtifactVersion, manifest_item["artifact_version_id"])

    download = client.get(
        f"/api/artifact-versions/{manifest_item['artifact_version_id']}/download"
    )
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/json")
    assert f"sha256:{hashlib.sha256(download.content).hexdigest()}" == (
        version.content_hash
    )


@pytest.mark.postgres
@pytest.mark.integration
def test_missing_artifact_download_uses_stable_error(db_session) -> None:
    app = create_app()

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as local_client:
        response = local_client.get(
            "/api/artifact-versions/00000000-0000-0000-0000-000000000000/download"
        )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ARTIFACT_NOT_FOUND"
