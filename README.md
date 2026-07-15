# AI 论文自动化生产平台

本仓库是平台代码的唯一 Git 事实源。当前分支 `feat/p1-1-platform-ingest-loop` 实现 P1-1：可运行的平台骨架与资料摄取闭环。

## 当前模块

- `platform/`：FastAPI、PostgreSQL、Redis Stream、Outbox Publisher、Worker、Ingest CLI Adapter、Artifact Store、Vue 3 管理端、Docker Compose 和跨电脑迁移工具。
- `ingest-cli/`：已冻结的 Ingest CLI v0.1 离线参考实现；平台只通过 Adapter 调用，不复制治理规则。
- `docs/ingest-governance-v0.1/`：资料治理冻结契约验证器。
- `uiux-prototype/`：已冻结 UI/UX 评审原型。
- `project-fact-p0-r6/`：冻结 UI 原型仍需读取的历史执行夹具，不属于 P1-1 自动执行范围。

ProjectFact r2-r5 失败候选和 NSTL 临时抓取文件已从当前代码树移除，其历史仍可从 Git 追溯。

## P1-1 固定闭环

```text
创建任务 → TASK_START 人工批准 → material_ingest 入队
→ PostgreSQL Outbox → Redis Stream → Worker Lease / Attempt
→ 真实 Ingest CLI scan + verify → ArtifactVersion
→ material_ingest SUCCEEDED
→ project_fact_review WAITING_FOR_APPROVAL
```

PostgreSQL 是唯一业务事实源；Redis 只保存可重建的工作通知。没有 SQLite、内存 Redis 正式链路或前端核心 Mock。

## 新电脑启动

新电脑安装并启动 Docker Desktop 后，不需要单独安装 PostgreSQL 或 Redis：

```powershell
Copy-Item platform/.env.example platform/.env
# 修改 platform/.env 中的本地密码
platform/scripts/bootstrap-new-machine.ps1
```

- 管理端：`http://127.0.0.1:5173`
- API：`http://127.0.0.1:8000`
- 健康检查：`http://127.0.0.1:8000/api/system/health`

## 本机源码运行

```powershell
cd platform/backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pip install -e ..\..\ingest-cli
$env:DATABASE_URL='postgresql+psycopg://...'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

独立启动 Publisher 与 Worker：

```powershell
python -m app.outbox.main
python -m app.worker.main
```

前端：

```powershell
cd platform/frontend
npm ci
npm run dev
```

## 验证与迁移

```powershell
platform/scripts/test-all.ps1
platform/scripts/test-all.ps1 -WithRedis
platform/scripts/test-all.ps1 -Docker -E2E
```

数据库、Artifact 备份恢复和跨电脑迁移见 `platform/docs/P1-1_DATA_PORTABILITY.md`。P1-1 在真实 Docker/Redis、故障恢复、Playwright E2E、备份恢复和截图全部通过前不得标记为完成。
