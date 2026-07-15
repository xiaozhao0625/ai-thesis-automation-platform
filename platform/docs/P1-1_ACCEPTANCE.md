# P1-1 验收记录

更新日期：2026-07-16
当前结论：**未完成，等待 Docker/Redis 电脑执行最终验收**。

## 当前电脑已验证

- Ingest CLI：181 passed；
- 冻结治理契约：188 passed；
- P1-1 后端：57 passed、1 Redis integration skipped；
- 前端 Vitest：9 passed；
- TypeScript：通过；
- Vite production build：通过；
- PostgreSQL 17.10：Alembic downgrade/upgrade 循环通过；
- 真实 CLI Adapter：128 文件 scan + verify 通过；
- Artifact：10 个当前 ArtifactVersion，逐文件内容寻址归档；
- 迁移工具：备份 Manifest 已覆盖表行数、Artifact 文件统计；恢复后逐表、逐文件 Hash 核验；
- Docker 验收入口：可在一次性容器内运行 CLI、后端、前端和 Playwright，不要求新电脑单独安装 PostgreSQL/Redis；
- 浏览器：创建任务、人工批准、QUEUED 节点与 Outbox 真实显示；
- 浏览器控制台：无 error/warn；
- 无 Redis 时：系统健康明确显示 Redis 不可用，节点不伪装成功。

## 等待 Docker 电脑验证

- [ ] Compose PostgreSQL/Redis 健康；
- [ ] Outbox → Redis Stream → Worker；
- [ ] material_ingest 真实经历 RUNNING → SUCCEEDED；
- [ ] project_fact_review = WAITING_FOR_APPROVAL；
- [ ] 真实 Redis 重复消息幂等；
- [ ] Redis 暂不可用后 Publisher 恢复；
- [ ] Worker 中断、Lease 过期和 Attempt 保留；
- [ ] CLI 失败最多三次；
- [ ] Playwright 全闭环；
- [ ] 下载 Manifest 并校验 Hash；
- [ ] 刷新后状态保持；
- [ ] backup → 新数据库 restore → Artifact 校验；
- [ ] 至少六张真实运行截图；
- [ ] 唯一根 `handoff.md` 更新；
- [ ] 最终 Git clean、本地提交、未推送。

## Docker 验收命令

```powershell
platform/scripts/bootstrap-new-machine.ps1
platform/scripts/test-all.ps1 -Docker -E2E
```

在以上待办全部完成前，不得把 P1-1 标记为完成。
