# P1-1 平台骨架与资料摄取真实闭环设计规格

状态：待书面确认  
分支：`feat/p1-1-platform-ingest-loop`  
父提交：`819783a`  
冻结依赖：资料治理契约 `8d0e9fa`、Ingest CLI `2938073`、UI/UX v1.2.3

## 1. 目标与边界

P1-1 交付一个可启动、可操作、可观察、可恢复的最小平台成品。唯一业务闭环为：

```text
创建 Task
→ TASK_START 人工批准
→ 创建 WorkflowRun 和三个固定 NodeRun
→ material_ingest READY / QUEUED
→ Outbox 发布到 Redis Stream
→ Worker 获取数据库 Lease 并创建 Attempt
→ 真实调用既有 Ingest CLI scan + verify
→ 归档正式输出并建立 ArtifactVersion
→ material_ingest SUCCEEDED
→ project_fact_review WAITING_FOR_APPROVAL
→ Web 展示数据库中的真实结果
```

本阶段不实现正文生成、模型网关、官方实时检索、DOCX、自动 ProjectFact 提取、后续审批或历史论文库导入。不得修改冻结资料治理包，不得复制 CLI 的分类、Hash、路径或候选规则。

## 2. 关键架构决策

采用同一仓库、同一后端代码库的模块化单体，部署时拆成三个进程：

1. FastAPI：同步命令、查询、审批和下载；
2. Outbox Publisher：从 PostgreSQL 读取待发布事件并写入 Redis Stream；
3. Worker：消费 Redis Stream，使用 PostgreSQL Lease 执行节点。

PostgreSQL 是唯一业务事实来源。Redis 只承载允许重复的工作通知，不保存不可恢复的业务状态。Web 只从 API 读取状态，不持有核心演示 Mock。

不采用 API 内嵌后台线程，因为它无法可靠覆盖多进程、重启和中断恢复；不提前拆微服务，因为会扩大 P1-1 的部署、契约和运维范围。

## 3. 仓库结构

```text
platform/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── artifacts/
│   │   ├── core/
│   │   ├── db/
│   │   ├── domain/
│   │   ├── ingest_adapter/
│   │   ├── outbox/
│   │   ├── worker/
│   │   ├── workflow/
│   │   └── main.py
│   ├── alembic/
│   ├── tests/
│   └── pyproject.toml
├── frontend/
├── deploy/docker-compose.yml
├── benchmark/ingest-fixture-v1/
├── artifact_store/                 # 运行时目录，Git 忽略
├── docs/
└── scripts/
```

既有 `ingest-cli/` 保持独立，不迁入 `platform/backend`。Adapter 通过当前 Python 解释器调用已安装的 `thesis_ingest` 包；开发脚本负责以 editable 方式安装既有 CLI，容器镜像则在构建时安装它。

## 4. 数据模型与状态约束

数据库使用 UUID 主键、UTC 时区时间和数据库枚举/检查约束。SQLAlchemy 2.x 模型与 Alembic 是唯一表结构来源。

### 4.1 核心实体

- `tasks`：标题、状态、能力包、受控 `source_mount_path`、创建人和时间；
- `human_approvals`：仅 `TASK_START`，状态、决定、操作人、意见和时间；
- `workflow_runs`：固定定义版本 `p1-1.v1`；
- `node_runs`：固定节点键、状态、执行指纹、Attempt 计数和当前输出数；
- `node_execution_attempts`：不可变执行历史；
- `outbox_events`：事件载荷、发布状态和次数；
- `worker_leases`：Lease token、有效期、heartbeat 和终态；
- `artifacts`、`artifact_versions`、`node_run_outputs`：不可覆盖的产物版本和当前输出关系；
- `node_run_logs`：结构化 Worker/CLI 日志，支持按节点读取；
- `worker_instances`：Worker 心跳与当前执行状态，用于系统页观测。

### 4.2 工作流状态

`NodeRun.status` 限定为：

```text
PENDING READY QUEUED RUNNING WAITING_FOR_APPROVAL
SUCCEEDED FAILED RETRYING BLOCKED INVALIDATED
```

P1-1 固定节点：

- `task_start_approval`：创建时 `WAITING_FOR_APPROVAL`，人工批准后 `SUCCEEDED`；
- `material_ingest`：`PENDING → READY → QUEUED → RUNNING → SUCCEEDED`，失败时按策略进入 `RETRYING` 或 `FAILED`；
- `project_fact_review`：初始 `PENDING`，摄取成功后进入 `WAITING_FOR_APPROVAL`，本阶段不继续推进。

数据库约束保证每个 WorkflowRun 的节点键唯一、每个 NodeRun 的 Attempt 编号唯一、每个 Artifact 的版本号唯一、每个输出角色最多一个当前版本。活跃 Lease 由 PostgreSQL 部分唯一索引约束为每个 NodeRun 最多一个。

## 5. 审批与原子事务

Task 创建在一个事务中写入：

- Task=`WAITING_FOR_APPROVAL`；
- `TASK_START` Approval=`PENDING`；
- WorkflowRun=`WAITING_FOR_APPROVAL`；
- 三个固定 NodeRun。

审批通过在一个事务中：

- Approval=`APPROVED`；
- `task_start_approval=SUCCEEDED`；
- `material_ingest=READY`；
- Task/WorkflowRun=`RUNNING`。

随后由调度服务在一个事务中完成强制一致性边界：

```text
material_ingest = QUEUED
+ OutboxEvent(event_type=MATERIAL_INGEST_REQUESTED, status=PENDING)
```

重复审批使用行锁和状态前置条件，返回原结果或稳定冲突错误，不生成第二个 WorkflowRun 或 OutboxEvent。

## 6. Outbox、Redis 与 Worker

### 6.1 Redis 契约

使用 Redis Stream 和固定 consumer group，不使用无确认语义的 List：

- Stream：`thesis:node-jobs:v1`；
- Consumer group：`material-workers:v1`；
- 消息含 `event_id`、`node_run_id`、`execution_fingerprint`、`event_type`；
- Publisher 可因进程中断重复 `XADD`；Worker 必须幂等；
- Worker 只在数据库终态提交后 `XACK`；未确认消息可由其他 Worker 重新 claim。

Publisher 对 PENDING Outbox 行使用 `FOR UPDATE SKIP LOCKED`。Redis 写入成功后才将行标记为 PUBLISHED；若在两者之间崩溃，数据库仍为 PENDING，后续产生重复消息但不丢任务。

### 6.2 Lease 与 Attempt

Worker 消费消息后在数据库事务中校验节点与执行指纹，获取 60 秒 Lease，创建新的 Attempt，更新节点为 RUNNING。执行期间每 15 秒更新 Lease、Attempt 和 Worker heartbeat。

幂等键为：

```text
node_run_id + execution_fingerprint
```

同一幂等键已有 SUCCEEDED 当前输出时，重复消息直接确认；已有有效 Lease 时不并发执行；Lease 过期后保留旧 Attempt 并创建新的 Attempt。最大 Attempt 为 3。

恢复协调器处理：

- 过期 RUNNING Lease：Attempt 标记失败，节点进入 RETRYING/FAILED；
- QUEUED/RETRYING 且没有有效 Lease：生成新的 OutboxEvent；
- 已成功但 Redis 消息未确认：幂等跳过并确认；
- Redis 暂不可用：Outbox 保持 PENDING，Publisher 指数退避。

## 7. Ingest CLI Adapter

Adapter 的职责严格限定为编排：

1. 验证输入路径位于配置的受控根目录；
2. 拒绝仓库根、系统目录、Artifact Store 和输出目录自身；
3. 在 Attempt 临时目录生成 CLI 配置；
4. 使用 `sys.executable -m thesis_ingest scan` 调用既有 CLI；
5. 捕获 stdout、stderr、退出码和结构化日志；
6. 使用 `python -m thesis_ingest verify` 校验输出；
7. 校验 Manifest 状态、Schema、引用与输出 Hash；
8. 返回正式文件清单和统计，不解释或重算 CLI 规则。

源资料以只读方式访问。业务身份继续使用 `source_mount_id + relative_path + content_hash`；不得把绝对根路径作为 Artifact 身份。P1-1 默认仅开放仓库内 `platform/benchmark/ingest-fixture-v1`，外部目录必须显式加入允许根配置。

## 8. Artifact Store

运行时产物采用“临时 staging → Hash 校验 → 原子重命名 → 数据库提交”。相对路径结构为：

```text
tasks/{task_id}/nodes/{node_run_id}/attempts/{attempt_id}/{sha256}/{filename}
```

数据库不保存机器绝对根路径。`ArtifactVersion.relative_storage_path` 相对于 `ARTIFACT_STORE_ROOT`，因此换电脑后只需恢复 Artifact Store 并修改环境根目录。

归档角色至少覆盖正式契约列出的九类输出。旧版本永不覆盖；新的成功 Attempt 仅切换 `NodeRunOutput.is_current`。下载接口重新计算文件 Hash，路径解析必须保持在 Artifact Store 内。

## 9. API 与错误契约

实现指令规定的健康、任务、审批、工作流、节点、日志、摄取、下载和系统端点。响应使用稳定 JSON 字段，错误统一为：

```json
{
  "error": {
    "code": "STABLE_ERROR_CODE",
    "message": "可读说明",
    "request_id": "uuid",
    "details": {}
  }
}
```

重点错误码包括：`INVALID_STATE_TRANSITION`、`APPROVAL_ALREADY_DECIDED`、`SOURCE_PATH_NOT_ALLOWED`、`SOURCE_PATH_NOT_FOUND`、`OUTBOX_PUBLISH_FAILED`、`LEASE_NOT_AVAILABLE`、`LEASE_EXPIRED`、`INGEST_SCAN_FAILED`、`INGEST_VERIFY_FAILED`、`ARTIFACT_HASH_MISMATCH`、`ARTIFACT_NOT_FOUND`。

## 10. Vue 管理端

前端继承 UI/UX v1.2.3 Spectrum Ledger 的布局、色彩和路由语义，使用 Vue 3、TypeScript、Vite、Vue Router 和 Pinia。P1-1 接入真实页面：

- 运营工作台；
- 任务列表和新建任务；
- TASK_START 审批中心；
- 任务总览；
- 工作流 DAG 与节点检查器；
- 项目与材料统计、ArtifactVersion 列表和下载；
- Worker/Outbox 系统状态。

中文为主名称，技术 ID 为次级信息；1280px 可操作；无聊天界面。Pinia 只缓存 API 结果，刷新后重新请求。所有加载、空、失败、重试和不可用状态必须显式呈现。

## 11. 受控基准夹具

创建 100–250 个可入库、无隐私、无真实凭证、无大文件的确定性夹具，包含任务书、项目说明、源码、测试、迁移、模板、官方资料快照、截图、重复项、备份、`.venv`、缓存、可执行文件、裸引用和敏感测试配置。

夹具生成器必须可重复，Manifest 固定并有测试校验。不得引用或扫描历史论文库。

## 12. 跨电脑数据可移植性

### 12.1 原则

禁止复制 PostgreSQL 安装目录或原始 data directory 作为交接方式。新电脑只需 Docker Desktop；PostgreSQL 和 Redis 由 Compose 创建。

三类内容分开迁移：

| 内容 | 标准载体 | 恢复方式 |
|---|---|---|
| 表结构 | Alembic migrations | `alembic upgrade head` |
| 业务数据 | PostgreSQL custom-format logical dump | `pg_restore` 到全新空数据库 |
| Artifact 文件 | ZIP + SHA-256 清单 | 解压到新 Artifact Store 并逐项核验 |

Redis 数据不迁移。Outbox、NodeRun 和 Lease 均在 PostgreSQL；恢复后由协调器重新发布缺失通知。

### 12.2 新环境启动

`scripts/bootstrap-new-machine.ps1` 负责：

1. 校验 Docker/Compose 和 `.env`；
2. 启动 PostgreSQL、Redis；
3. 等待健康状态；
4. 执行 Alembic；
5. 安装/校验受控基准夹具；
6. 启动 API、Publisher、Worker、Frontend；
7. 执行健康和版本检查。

### 12.3 备份与恢复

`scripts/backup-data.ps1` 在停止写入或进入维护模式后生成：

```text
handoff-bundle/
├── database.dump
├── artifact-store.zip
├── backup-manifest.json
├── checksums.sha256
└── RESTORE.md
```

Manifest 记录 Git commit、Alembic revision、PostgreSQL/Redis 镜像、时间、行数、文件数和 Hash。备份目录、dump、运行时 Artifact 和 `.env` 均不提交 Git。

`scripts/restore-data.ps1` 默认拒绝非空目标，创建新的恢复数据库，校验全部 Hash 后 `pg_restore --no-owner --no-acl --exit-on-error`，再运行 Alembic 前向升级。随后恢复 Artifact，逐项比对 `ArtifactVersion.content_hash`，等待旧 Lease 失效并运行恢复协调器。验证成功后才允许切换 `DATABASE_URL`。

如新电脑无网络，可额外使用 `docker save/load` 携带锁定的 PostgreSQL、Redis 和应用镜像；在线模式则按 Compose 中的固定版本拉取。验收机记录实际镜像 digest。

## 13. 测试策略与分阶段验收

严格 TDD：每项生产代码先有失败测试，再实现最小逻辑。

今天在当前电脑完成：

- CLI 既有测试和冻结契约；
- 纯领域状态机、API、Artifact、Adapter、Outbox 编码和 Worker 幂等单元测试；
- 使用本机真实 PostgreSQL 的迁移和集成测试；
- Vue 组件、Store、路由和类型检查；
- Docker Compose 配置、脚本和文档静态校验。

真实 Redis 不用内存实现替代。需要 Redis 的测试保留为独立 integration marker，在没有 Redis 时明确 SKIPPED/PENDING，不计入完成。

明天在安装 Docker Desktop 的电脑完成正式验收：

- Docker Compose 启动 PostgreSQL/Redis；
- PostgreSQL/Redis 全集成；
- Outbox → Redis Stream → Worker → CLI → Artifact 真实闭环；
- Redis 中断、Worker 中断、Lease 过期、CLI 失败、重复消息、源路径不存在；
- Playwright 真实 E2E 和浏览器控制台检查；
- 至少六张真实运行截图；
- 备份、全新数据库恢复、Artifact Hash 和恢复协调器验证。

未运行的 Redis/Docker/E2E 测试不得标为通过，P1-1 在上述正式验收全部完成前保持“未完成”。

## 14. 安全与审计

- `.env`、密码、dump、运行日志和 Artifact Store 不提交；
- API 不接受任意系统路径；
- 所有下载防止路径穿越并复核 Hash；
- Worker 子进程使用参数数组，不拼接 shell 命令；
- 源目录只读，CLI 输出仅写到 Attempt 临时目录；
- 审批、状态迁移、Attempt、Lease、发布和下载保留审计时间与操作主体；
- 健康接口不泄露连接串、密码或文件系统绝对路径。

## 15. 完成交付

交付代码、Alembic、Compose、脚本、测试、README、`.env.example`、API/实施/验收/数据可移植性文档、阶段报告、至少六张截图以及唯一根级 `handoff.md` 更新。

最终只在功能、可靠性、PostgreSQL/Redis 集成、前端、E2E、备份恢复和 CLI 回归全部通过后声明 P1-1 完成。分支本地提交并保持 clean，不推送、不创建 Pull Request、不删除历史分支或 worktree。
