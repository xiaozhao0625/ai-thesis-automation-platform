# P1-1 实施说明

## 1. 运行拓扑

P1-1 是模块化单体代码库、分进程运行：

```text
Vue 管理端
  ↓ HTTP
FastAPI ───────────────→ PostgreSQL
                           ↑
Outbox Publisher ─→ Redis Stream ─→ Worker
                                      ↓
                              Ingest CLI Adapter
                                      ↓
                               Local Artifact Store
```

FastAPI、Publisher 和 Worker 复用 `platform/backend/app` 中的模型和应用服务，但生命周期相互独立。PostgreSQL 保存 Task、审批、工作流、节点、Attempt、Lease、Outbox 和 ArtifactVersion。Redis Stream 只传递至少一次的工作通知。

## 2. 数据库

首个 Alembic revision：`2c13448999a3`。

| 表 | 责任 |
|---|---|
| `tasks` | 论文任务与受控资料挂载 |
| `human_approvals` | TASK_START 人工决定 |
| `workflow_runs` | P1-1 固定工作流实例 |
| `node_runs` | 三个逻辑节点与当前状态 |
| `node_execution_attempts` | 不可变执行尝试 |
| `worker_leases` | 60 秒 Lease 与 15 秒 heartbeat |
| `outbox_events` | PostgreSQL 到 Redis 的可靠投递源 |
| `artifacts` / `artifact_versions` | 不可覆盖的产物及版本 |
| `node_run_outputs` | 节点当前输出角色 |
| `node_run_logs` | 状态迁移与执行日志 |
| `worker_instances` | Worker 运行观测 |

活跃 Lease 使用 PostgreSQL 部分唯一索引保证每个 NodeRun 最多一个。NodeRunOutput 同样使用部分唯一索引保证每个输出角色最多一个当前版本。

## 3. 事务边界

创建任务一次写入 Task、TASK_START Approval、WorkflowRun 和三个 NodeRun。

批准启动一次事务完成：

```text
Approval = APPROVED
task_start_approval = SUCCEEDED
material_ingest = QUEUED
Task / WorkflowRun = RUNNING
OutboxEvent = PENDING
```

READY 和 QUEUED 都写入 `node_run_logs`。重复批准返回 `APPROVAL_ALREADY_DECIDED`，不产生第二个 Outbox。

## 4. Outbox 与 Redis Stream

- Stream：`thesis:node-jobs:v1`；
- Consumer group：`material-workers:v1`；
- Publisher 使用 `FOR UPDATE SKIP LOCKED`；
- Redis 写入失败时 Outbox 保持 PENDING；
- Redis 写入成功、数据库提交前崩溃可能产生重复消息；
- Worker 使用 `node_run_id + execution_fingerprint` 幂等；
- Worker 只在数据库结果提交后确认 Redis 消息；
- 未确认消息通过 `XAUTOCLAIM` 交给其他 Worker。

## 5. Worker

Worker 消费消息后获取数据库 Lease、创建 Attempt 并提交 RUNNING，随后使用独立数据库会话每 15 秒 heartbeat。Lease TTL 为 60 秒。过期 Lease 保留失败 Attempt，节点重新排队；第三次失败后进入 FAILED。

恢复入口：

```powershell
python -m app.worker.recover --expire-active
```

用于跨电脑恢复时终止旧机器 Lease，并为可恢复节点生成新 Outbox。

## 6. Ingest CLI Adapter

Adapter 只做以下编排：

1. 将配置路径解析到允许的 benchmark 根；
2. 拒绝绝对路径、`..`、UNC、Artifact Store 和不存在目录；
3. 生成 Attempt 临时配置；
4. 使用参数数组调用 `python -m thesis_ingest scan`；
5. 调用 CLI `verify`；
6. 检查冻结的十个输出文件和 COMPLETED Manifest；
7. 把结果交给 Artifact Store。

分类、Hash、路径、去重、候选和敏感标记全部由既有 CLI 执行。

## 7. Artifact Store

```text
tasks/{task_id}/nodes/{node_run_id}/attempts/{attempt_id}/{sha256}/{filename}
```

相对路径写入数据库；根路径来自环境变量。归档采用 staging、SHA-256 复核和原子重命名。下载前重新计算 Hash，并拒绝路径逃逸。旧 ArtifactVersion 不覆盖。

## 8. 前端

Vue 管理端实现工作台、任务、新建、审批、总览、工作流节点检查器、材料清单、Worker 与 Outbox 页面。刷新后从 API 重建状态。生产构建使用同源 `/api`，Nginx 反向代理到 FastAPI；本地 Vite 使用开发代理，因此浏览器、宿主机和 Docker E2E 不依赖硬编码容器地址。Spectrum Ledger 使用 232px 导航、56px 顶栏、阶段色轨和 360px 检查器；1280px 保持可操作。

## 9. 当前受控夹具

`platform/benchmark/ingest-fixture-v1` 含 128 个合成文件。`fixture-manifest.json` 固定每个文件的 SHA-256。夹具无真实隐私、无真实凭证、无大文件，不引用历史论文库。

## 10. Docker 验收

生产 Compose 仍只有 PostgreSQL、Redis、API、Publisher、Worker 和 Frontend 六个服务。`docker-compose.test.yml` 只在验收时增加一次性 Backend、Frontend 和 Playwright 容器；Playwright 镜像与 `package-lock.json` 的 1.61.1 精确匹配。运行：

```powershell
platform/scripts/test-all.ps1 -Docker -E2E
```

该命令创建独立 `thesis_platform_test` 数据库，不清空正式 `thesis_platform`；依次执行冻结 CLI、后端（含真实 PostgreSQL/Redis）、前端单测/类型/构建和真实 E2E。
