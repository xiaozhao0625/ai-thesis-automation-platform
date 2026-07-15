# AI 论文自动化生产平台

本仓库是平台代码的唯一 Git 仓库。当前开发分支 `feat/p1-1-platform-ingest-loop` 正在实现 P1-1：平台可运行骨架与真实资料摄取闭环。

## 当前模块

- `platform/`：FastAPI、PostgreSQL、Redis Stream、Outbox Publisher、Worker、Ingest CLI Adapter、Artifact Store、Vue 3 管理端、Docker Compose 和跨电脑迁移工具；
- `ingest-cli/`：已冻结的 Ingest CLI v0.1 离线参考实现，本阶段只通过 Adapter 调用，不复制规则；
- `docs/ingest-governance-v0.1/`：资料治理冻结契约验证器；
- `uiux-prototype/`：历史 UI/UX 评审原型，P1-1 管理端继承已冻结 v1.2.3 的 Spectrum Ledger 视觉与路由语义；
- `project-fact-p0-r*`：ProjectFact 历史评审候选，不属于 P1-1 自动执行范围。

## P1-1 固定闭环

```text
创建任务 → TASK_START 人工批准 → material_ingest 入队
→ PostgreSQL Outbox → Redis Stream → Worker Lease / Attempt
→ 真实 Ingest CLI scan + verify → ArtifactVersion
→ material_ingest SUCCEEDED
→ project_fact_review WAITING_FOR_APPROVAL
```

PostgreSQL 是唯一业务事实来源；Redis 只保存可重建的工作通知。不存在 SQLite 或内存 Redis 正式链路，也没有前端核心 Mock。

## Docker 新电脑启动

新电脑只需安装并启动 Docker Desktop，不需要单独安装 PostgreSQL 或 Redis：

```powershell
Copy-Item platform/.env.example platform/.env
# 修改 platform/.env 中的本地密码
platform/scripts/bootstrap-new-machine.ps1
```

入口：

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
npm install
npm run dev
```

## 测试

```powershell
# 当前电脑已安装 Python/Node 时：
platform/scripts/test-all.ps1
# Docker Redis 可用时：
platform/scripts/test-all.ps1 -WithRedis
# 新电脑仅依赖 Docker 的完整验收（含 Redis 与 Playwright）：
platform/scripts/test-all.ps1 -Docker -E2E
```

数据备份、恢复和新电脑迁移见 `platform/docs/P1-1_DATA_PORTABILITY.md`。P1-1 在真实 Docker/Redis、故障恢复、Playwright E2E、备份恢复和截图全部通过前不得标记为完成。
