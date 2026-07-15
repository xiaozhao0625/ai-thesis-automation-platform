# P1-1 平台骨架与资料摄取闭环实施计划

设计规格：`docs/superpowers/specs/2026-07-16-p1-1-platform-ingest-loop-design.md`

## 执行纪律

- 所有功能严格按 RED → GREEN → REFACTOR 执行；
- 每个小节完成后运行定向测试，阶段结束运行全量回归；
- 不修改冻结治理契约，不复制 Ingest CLI 规则；
- 无真实 Redis/Docker 时相关集成测试必须明确跳过，不计入完成；
- 不推送、不创建 PR、不删除历史分支或 worktree。

## Task 1：后端工程与领域状态机

1. 建立 `platform/backend` Python 工程、配置、数据库会话和测试骨架；
2. 先写 Task/Approval/Workflow/Node 状态迁移单元测试；
3. 实现枚举、实体和领域服务；
4. 验证非法迁移、重复审批和固定三节点。

## Task 2：PostgreSQL 模型与 Alembic

1. 先写模型约束和迁移集成测试；
2. 实现 SQLAlchemy 2.x 模型；
3. 创建首个 Alembic migration；
4. 在本机 PostgreSQL 运行 upgrade/downgrade/upgrade；
5. 验证唯一约束、外键、部分唯一索引和 UTC 时间。

## Task 3：Task、审批和工作流 API

1. 先写 API 契约失败测试；
2. 实现统一错误结构与 request id；
3. 实现 Task 创建/列表/详情；
4. 实现审批列表与决定；
5. 验证审批事务同时生成 QUEUED NodeRun 与 PENDING Outbox。

## Task 4：Outbox Publisher 与 Redis 契约

1. 先写消息编码、重复发布和失败保留测试；
2. 实现 Redis Stream 网关；
3. 实现 Publisher 扫描和发布循环；
4. 编写真实 Redis integration marker；
5. 验证无 Redis 时应用可启动、Publisher 明确报告不可用。

## Task 5：Worker、Lease、Attempt 与恢复协调器

1. 先写 Lease 获取、heartbeat、过期、重试和幂等测试；
2. 实现 Worker 注册、消息消费和 Attempt 生命周期；
3. 实现恢复协调器；
4. 验证最大 3 次、重复消息无重复当前产物；
5. 编写真实 Redis/PostgreSQL 联合集成测试。

## Task 6：Ingest CLI Adapter 与 Artifact Store

1. 先写受控路径、子进程命令、失败、verify 和 Hash 测试；
2. 实现真实 CLI Adapter；
3. 实现 staging、内容寻址归档和安全下载；
4. 实现 Artifact/Version/Output 原子提交；
5. 用既有 CLI 小夹具运行真实 Adapter 集成测试。

## Task 7：受控基准夹具

1. 先写文件数量、分类覆盖和确定性测试；
2. 创建固定生成器和基准 Manifest；
3. 生成 100–250 个无隐私、无凭证、无大文件的夹具；
4. 验证不包含历史论文库路径。

## Task 8：查询、下载与系统 API

1. 先写 Workflow、Attempt、日志、摄取摘要、Artifact 下载、Worker/Outbox 测试；
2. 实现查询 DTO 和分页；
3. 实现下载路径穿越与 Hash 复核；
4. 实现 `/health` 与 `/api/system/health`。

## Task 9：Vue 3 管理端

1. 建立 Vue/TypeScript/Vite/Router/Pinia/Vitest；
2. 先写 API client、Store、路由和关键组件测试；
3. 实现 Spectrum Ledger 壳层；
4. 实现工作台、任务、新建、审批、总览、工作流、材料和系统页；
5. 验证 loading/empty/error/refresh 和 1280px 布局；
6. 加入 Playwright E2E。

## Task 10：Docker、运行脚本与数据可移植性

1. 编写 Dockerfile、Compose、`.env.example`；
2. 实现 `dev-up/dev-down/test-all`；
3. 先写脚本静态与拒绝非空恢复测试；
4. 实现 bootstrap、backup、restore、verify 和 reconcile；
5. 编写数据可移植性文档与离线镜像流程。

## Task 11：全量验证与交付

1. 运行 CLI 181、冻结契约 188；
2. 运行后端单元与 PostgreSQL 集成；
3. 运行前端测试、类型检查和构建；
4. 在 Docker 电脑运行 Redis/PG、真实闭环、故障恢复、E2E；
5. 生成至少六张真实截图；
6. 更新 README、实施/API/验收/迁移文档、阶段报告和唯一根 `handoff.md`；
7. 运行完整验证、提交、确认 Git clean 且未推送。
