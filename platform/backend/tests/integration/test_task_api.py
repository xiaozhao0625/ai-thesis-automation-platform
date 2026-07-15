from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_session
from app.main import create_app


@pytest.fixture
def client(db_session) -> TestClient:
    app = create_app()

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


@pytest.mark.postgres
@pytest.mark.integration
def test_task_approval_and_workflow_api_use_persisted_state(client: TestClient) -> None:
    created = client.post(
        "/api/tasks",
        json={
            "title": "实验室设备管理系统",
            "capability_pack": "python_web_management_v1",
            "source_mount_path": "benchmark/ingest-fixture-v1",
            "created_by": "operator-01",
        },
    )

    assert created.status_code == 201
    body = created.json()
    task_id = body["id"]
    approval_id = body["task_start_approval_id"]
    assert body["status"] == "WAITING_FOR_APPROVAL"

    listed = client.get("/api/tasks").json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == task_id

    approvals = client.get("/api/approvals").json()
    assert approvals["total"] == 1
    assert approvals["items"][0]["status"] == "PENDING"

    approved = client.post(
        f"/api/approvals/{approval_id}/decision",
        json={
            "decision": "APPROVE",
            "decided_by": "reviewer-01",
            "comment": "范围确认",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"

    workflow = client.get(f"/api/tasks/{task_id}/workflow")
    assert workflow.status_code == 200
    workflow_body = workflow.json()
    assert workflow_body["status"] == "RUNNING"
    assert [node["node_key"] for node in workflow_body["nodes"]] == [
        "task_start_approval",
        "material_ingest",
        "project_fact_review",
    ]
    assert workflow_body["nodes"][1]["status"] == "QUEUED"


@pytest.mark.postgres
@pytest.mark.integration
def test_missing_task_uses_stable_error_envelope(client: TestClient) -> None:
    response = client.get("/api/tasks/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TASK_NOT_FOUND"
    assert response.json()["error"]["request_id"]


@pytest.mark.postgres
@pytest.mark.integration
def test_health_endpoints_report_database_without_exposing_url(
    client: TestClient,
) -> None:
    assert client.get("/health").json() == {"status": "ok"}

    response = client.get("/api/system/health")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] == "ok"
    assert "postgresql" not in response.text.lower()


@pytest.mark.postgres
@pytest.mark.integration
def test_local_frontend_origin_is_allowed_by_cors(client: TestClient) -> None:
    response = client.options(
        "/api/tasks",
        headers={
            "origin": "http://127.0.0.1:5173",
            "access-control-request-method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "http://127.0.0.1:5173"
    )


@pytest.mark.postgres
@pytest.mark.integration
def test_task_api_rejects_arbitrary_absolute_source_path(client: TestClient) -> None:
    response = client.post(
        "/api/tasks",
        json={
            "title": "危险路径",
            "capability_pack": "python_web_management_v1",
            "source_mount_path": "C:/Windows",
            "created_by": "operator-01",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SOURCE_PATH_NOT_ALLOWED"
