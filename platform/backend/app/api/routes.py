from __future__ import annotations

from uuid import UUID

import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response, status
from redis import Redis
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.schemas import ApprovalDecisionRequest, TaskCreate
from app.artifacts.dependencies import get_artifact_store
from app.artifacts.store import ArtifactHashMismatch, LocalArtifactStore
from app.core.config import get_settings
from app.core.errors import ResourceNotFound
from app.db.models import (
    HumanApproval,
    Artifact,
    ArtifactVersion,
    NodeExecutionAttempt,
    NodeRun,
    NodeRunLog,
    OutboxEvent,
    Task,
    WorkerInstance,
    WorkflowRun,
    NodeRunOutput,
)
from app.db.session import get_session
from app.ingest_adapter.dependencies import get_source_resolver
from app.ingest_adapter.paths import ControlledSourceResolver
from app.workflow.service import TaskWorkflowService


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/system/health")
def system_health(session: Session = Depends(get_session)) -> dict[str, str]:
    database = "ok"
    redis_status = "ok"
    try:
        session.execute(text("select 1"))
    except Exception:
        database = "unavailable"
    settings = get_settings()
    try:
        client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.15,
            socket_timeout=0.15,
        )
        client.ping()
        client.close()
    except Exception:
        redis_status = "unavailable"
    return {
        "status": "ok" if database == redis_status == "ok" else "degraded",
        "database": database,
        "redis": redis_status,
    }


@router.post("/api/tasks", status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    session: Session = Depends(get_session),
    source_resolver: ControlledSourceResolver = Depends(get_source_resolver),
) -> dict[str, object]:
    source_resolver.resolve(payload.source_mount_path)
    created = TaskWorkflowService(session).create_task(**payload.model_dump())
    session.commit()
    return {
        **_task_payload(created.task),
        "task_start_approval_id": str(created.approval.id),
        "workflow_run_id": str(created.workflow.id),
    }


@router.get("/api/tasks")
def list_tasks(session: Session = Depends(get_session)) -> dict[str, object]:
    tasks = session.scalars(select(Task).order_by(Task.created_at.desc())).all()
    return {"items": [_task_payload(task) for task in tasks], "total": len(tasks)}


@router.get("/api/tasks/{task_id}")
def get_task(task_id: UUID, session: Session = Depends(get_session)) -> dict[str, object]:
    task = session.get(Task, task_id)
    if task is None:
        raise ResourceNotFound("TASK_NOT_FOUND", "task does not exist")
    return _task_payload(task)


@router.get("/api/approvals")
def list_approvals(session: Session = Depends(get_session)) -> dict[str, object]:
    rows = session.execute(
        select(HumanApproval, Task.title)
        .join(Task, Task.id == HumanApproval.task_id)
        .order_by(HumanApproval.submitted_at.desc())
    ).all()
    items = [
        {
            **_approval_payload(approval),
            "task_title": task_title,
        }
        for approval, task_title in rows
    ]
    return {"items": items, "total": len(items)}


@router.post("/api/approvals/{approval_id}/decision")
def decide_approval(
    approval_id: UUID,
    payload: ApprovalDecisionRequest,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    approval = TaskWorkflowService(session).decide_task_start(
        approval_id, **payload.model_dump()
    )
    session.commit()
    return _approval_payload(approval)


@router.get("/api/tasks/{task_id}/workflow")
def get_workflow(
    task_id: UUID, session: Session = Depends(get_session)
) -> dict[str, object]:
    workflow = session.scalar(
        select(WorkflowRun)
        .where(WorkflowRun.task_id == task_id)
        .order_by(WorkflowRun.created_at.desc())
    )
    if workflow is None:
        raise ResourceNotFound("WORKFLOW_NOT_FOUND", "workflow does not exist")
    nodes = session.scalars(
        select(NodeRun).where(NodeRun.workflow_run_id == workflow.id)
    ).all()
    order = {
        "task_start_approval": 0,
        "material_ingest": 1,
        "project_fact_review": 2,
    }
    nodes.sort(key=lambda node: order[node.node_key])
    return {
        "id": str(workflow.id),
        "task_id": str(workflow.task_id),
        "definition_version": workflow.definition_version,
        "status": workflow.status.value,
        "started_at": _iso(workflow.started_at),
        "finished_at": _iso(workflow.finished_at),
        "nodes": [_node_payload(node) for node in nodes],
    }


@router.get("/api/node-runs/{node_run_id}")
def get_node_run(
    node_run_id: UUID, session: Session = Depends(get_session)
) -> dict[str, object]:
    node = session.get(NodeRun, node_run_id)
    if node is None:
        raise ResourceNotFound("NODE_RUN_NOT_FOUND", "node run does not exist")
    return _node_payload(node)


@router.get("/api/node-runs/{node_run_id}/attempts")
def list_attempts(
    node_run_id: UUID, session: Session = Depends(get_session)
) -> dict[str, object]:
    attempts = session.scalars(
        select(NodeExecutionAttempt)
        .where(NodeExecutionAttempt.node_run_id == node_run_id)
        .order_by(NodeExecutionAttempt.attempt_number)
    ).all()
    return {
        "items": [
            {
                "id": str(item.id),
                "attempt_number": item.attempt_number,
                "worker_id": item.worker_id,
                "lease_id": str(item.lease_id) if item.lease_id else None,
                "status": item.status.value,
                "started_at": _iso(item.started_at),
                "heartbeat_at": _iso(item.heartbeat_at),
                "finished_at": _iso(item.finished_at),
                "error_code": item.error_code,
                "error_message": item.error_message,
            }
            for item in attempts
        ],
        "total": len(attempts),
    }


@router.get("/api/node-runs/{node_run_id}/logs")
def list_node_logs(
    node_run_id: UUID, session: Session = Depends(get_session)
) -> dict[str, object]:
    logs = session.scalars(
        select(NodeRunLog)
        .where(NodeRunLog.node_run_id == node_run_id)
        .order_by(NodeRunLog.sequence)
    ).all()
    return {
        "items": [
            {
                "sequence": item.sequence,
                "level": item.level,
                "event": item.event,
                "message": item.message,
                "details": item.details_json,
                "created_at": _iso(item.created_at),
            }
            for item in logs
        ],
        "total": len(logs),
    }


@router.get("/api/system/workers")
def list_workers(session: Session = Depends(get_session)) -> dict[str, object]:
    workers = session.scalars(
        select(WorkerInstance).order_by(WorkerInstance.id)
    ).all()
    return {
        "items": [
            {
                "id": worker.id,
                "status": worker.status.value,
                "current_node_run_id": (
                    str(worker.current_node_run_id)
                    if worker.current_node_run_id
                    else None
                ),
                "heartbeat_at": _iso(worker.heartbeat_at),
                "hostname": worker.hostname,
                "process_id": worker.process_id,
            }
            for worker in workers
        ],
        "total": len(workers),
    }


@router.get("/api/system/outbox")
def list_outbox(session: Session = Depends(get_session)) -> dict[str, object]:
    events = session.scalars(
        select(OutboxEvent).order_by(OutboxEvent.created_at.desc()).limit(100)
    ).all()
    pending = session.scalar(
        select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.status == "PENDING"
        )
    )
    return {
        "items": [
            {
                "id": str(event.id),
                "event_type": event.event_type,
                "aggregate_id": str(event.aggregate_id),
                "status": event.status.value,
                "publish_attempt_count": event.publish_attempt_count,
                "created_at": _iso(event.created_at),
                "published_at": _iso(event.published_at),
                "last_error": event.last_error,
            }
            for event in events
        ],
        "total": len(events),
        "pending": pending or 0,
    }


@router.get("/api/tasks/{task_id}/ingest/summary")
def get_ingest_summary(
    task_id: UUID,
    session: Session = Depends(get_session),
    store: LocalArtifactStore = Depends(get_artifact_store),
) -> dict[str, object]:
    summary_version = _current_output_version(
        session, task_id, "INGEST_SUMMARY"
    )
    manifest_version = _current_output_version(
        session, task_id, "INGEST_MANIFEST"
    )
    if summary_version is None or manifest_version is None:
        raise ResourceNotFound(
            "INGEST_RESULT_NOT_FOUND", "ingest result does not exist"
        )
    try:
        summary = json.loads(
            store.read_verified(
                summary_version.relative_storage_path,
                summary_version.content_hash,
            ).decode("utf-8")
        )
        manifest = json.loads(
            store.read_verified(
                manifest_version.relative_storage_path,
                manifest_version.content_hash,
            ).decode("utf-8")
        )
    except ArtifactHashMismatch as exc:
        raise ResourceNotFound(
            "ARTIFACT_HASH_MISMATCH", str(exc)
        ) from exc
    return {
        **summary,
        "manifest_status": manifest.get("status"),
        "summary_artifact_version_id": str(summary_version.id),
        "manifest_artifact_version_id": str(manifest_version.id),
    }


@router.get("/api/tasks/{task_id}/ingest/artifacts")
def list_ingest_artifacts(
    task_id: UUID, session: Session = Depends(get_session)
) -> dict[str, object]:
    rows = session.execute(
        select(NodeRunOutput, ArtifactVersion, Artifact)
        .join(
            ArtifactVersion,
            ArtifactVersion.id == NodeRunOutput.artifact_version_id,
        )
        .join(Artifact, Artifact.id == ArtifactVersion.artifact_id)
        .where(Artifact.task_id == task_id, NodeRunOutput.is_current.is_(True))
        .order_by(NodeRunOutput.output_role)
    ).all()
    items = [
        {
            "artifact_id": str(artifact.id),
            "artifact_version_id": str(version.id),
            "output_role": output.output_role,
            "version": version.version,
            "filename": version.original_filename,
            "content_hash": version.content_hash,
            "media_type": version.media_type,
            "size_bytes": version.size_bytes,
            "created_at": _iso(version.created_at),
            "download_url": f"/api/artifact-versions/{version.id}/download",
        }
        for output, version, artifact in rows
    ]
    return {"items": items, "total": len(items)}


@router.get("/api/artifact-versions/{artifact_version_id}/download")
def download_artifact(
    artifact_version_id: UUID,
    session: Session = Depends(get_session),
    store: LocalArtifactStore = Depends(get_artifact_store),
) -> Response:
    version = session.get(ArtifactVersion, artifact_version_id)
    if version is None:
        raise ResourceNotFound(
            "ARTIFACT_NOT_FOUND", "artifact version does not exist"
        )
    try:
        content = store.read_verified(
            version.relative_storage_path, version.content_hash
        )
    except (FileNotFoundError, ArtifactHashMismatch) as exc:
        raise ResourceNotFound(
            "ARTIFACT_HASH_MISMATCH", "artifact file is missing or corrupt"
        ) from exc
    encoded_name = quote(version.original_filename)
    return Response(
        content=content,
        media_type=version.media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
            "X-Content-SHA256": version.content_hash,
        },
    )


def _current_output_version(
    session: Session, task_id: UUID, output_role: str
) -> ArtifactVersion | None:
    return session.scalar(
        select(ArtifactVersion)
        .join(
            NodeRunOutput,
            NodeRunOutput.artifact_version_id == ArtifactVersion.id,
        )
        .join(Artifact, Artifact.id == ArtifactVersion.artifact_id)
        .where(
            Artifact.task_id == task_id,
            NodeRunOutput.output_role == output_role,
            NodeRunOutput.is_current.is_(True),
        )
    )


def _task_payload(task: Task) -> dict[str, object]:
    return {
        "id": str(task.id),
        "title": task.title,
        "status": task.status.value,
        "capability_pack": task.capability_pack,
        "source_mount_path": task.source_mount_path,
        "created_by": task.created_by,
        "created_at": _iso(task.created_at),
        "updated_at": _iso(task.updated_at),
    }


def _approval_payload(approval: HumanApproval) -> dict[str, object]:
    return {
        "id": str(approval.id),
        "task_id": str(approval.task_id),
        "approval_type": approval.approval_type.value,
        "status": approval.status.value,
        "submitted_by": approval.submitted_by,
        "decided_by": approval.decided_by,
        "decision": approval.decision.value if approval.decision else None,
        "comment": approval.comment,
        "submitted_at": _iso(approval.submitted_at),
        "decided_at": _iso(approval.decided_at),
    }


def _node_payload(node: NodeRun) -> dict[str, object]:
    return {
        "id": str(node.id),
        "workflow_run_id": str(node.workflow_run_id),
        "node_key": node.node_key,
        "display_name": node.display_name,
        "status": node.status.value,
        "execution_fingerprint": node.execution_fingerprint,
        "attempt_count": node.attempt_count,
        "max_attempts": node.max_attempts,
        "current_output_count": node.current_output_count,
        "created_at": _iso(node.created_at),
        "updated_at": _iso(node.updated_at),
    }


def _iso(value):
    return value.isoformat() if value is not None else None
