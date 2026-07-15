# P1-1 API 契约

默认地址：`http://127.0.0.1:8000`。JSON 字段使用 snake_case，ID 为 UUID，时间为 UTC ISO 8601。

## 健康

```http
GET /health
GET /api/system/health
```

`/api/system/health` 分别返回 `database` 与 `redis`，外部依赖不可用时为 `degraded`，不泄露连接串。

## 任务

```http
POST /api/tasks
GET  /api/tasks
GET  /api/tasks/{task_id}
```

```json
{
  "title": "实验室设备管理系统",
  "capability_pack": "python_web_management_v1",
  "source_mount_path": "benchmark/ingest-fixture-v1",
  "created_by": "operator"
}
```

`source_mount_path` 必须是配置允许根下的项目相对路径。

## 审批

```http
GET  /api/approvals
POST /api/approvals/{approval_id}/decision
```

```json
{
  "decision": "APPROVE",
  "decided_by": "operator",
  "comment": "资料范围确认"
}
```

允许决定：`APPROVE`、`REJECT`。已决定审批不可重复执行。

## 工作流与执行

```http
GET /api/tasks/{task_id}/workflow
GET /api/node-runs/{node_run_id}
GET /api/node-runs/{node_run_id}/attempts
GET /api/node-runs/{node_run_id}/logs
```

固定节点键：`task_start_approval`、`material_ingest`、`project_fact_review`。

## 摄取结果

```http
GET /api/tasks/{task_id}/ingest/summary
GET /api/tasks/{task_id}/ingest/artifacts
GET /api/artifact-versions/{artifact_version_id}/download
```

下载响应包含 `X-Content-SHA256`，服务端在返回前复核文件 Hash。

## 系统

```http
GET /api/system/workers
GET /api/system/outbox
```

## 错误

```json
{
  "error": {
    "code": "SOURCE_PATH_NOT_ALLOWED",
    "message": "source path is outside configured roots",
    "request_id": "uuid",
    "details": {}
  }
}
```

主要错误码：

- `TASK_NOT_FOUND`
- `APPROVAL_NOT_FOUND`
- `APPROVAL_ALREADY_DECIDED`
- `INVALID_STATE_TRANSITION`
- `SOURCE_PATH_NOT_ALLOWED`
- `SOURCE_PATH_NOT_FOUND`
- `EXECUTION_FINGERPRINT_MISMATCH`
- `LEASE_NOT_AVAILABLE`
- `LEASE_EXPIRED`
- `MAX_ATTEMPTS_EXCEEDED`
- `INGEST_SCAN_FAILED`
- `INGEST_VERIFY_FAILED`
- `INGEST_RESULT_NOT_FOUND`
- `ARTIFACT_NOT_FOUND`
- `ARTIFACT_HASH_MISMATCH`
