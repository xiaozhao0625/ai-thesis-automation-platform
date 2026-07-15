# P1-1 数据可移植性与新电脑交接

## 结论

不要复制 PostgreSQL 安装目录，也不要复制原始 `data` directory。新电脑只安装 Docker Desktop；表结构由 Alembic 创建，业务数据通过 PostgreSQL 逻辑备份迁移，Artifact Store 独立归档并校验。

| 内容 | 载体 | 新电脑恢复方式 |
|---|---|---|
| PostgreSQL/Redis 运行环境 | Docker 镜像 | Docker Compose 创建 |
| 表、索引、约束 | Alembic migration | `alembic upgrade head` |
| 基准夹具 | Git 文件 + SHA-256 Manifest | 随代码获得并校验 |
| 业务数据 | `pg_dump -Fc` | `pg_restore` 到全新数据库 |
| Artifact 文件 | ZIP | 解压并与数据库 Hash 对照 |
| Redis 队列 | 不迁移 | PostgreSQL Outbox/恢复协调器重建 |
| 密码和本机路径 | `.env` | 新电脑重新配置，不进入 Git |

## 为什么不复制 PostgreSQL data directory

原始目录绑定 PostgreSQL 主版本、补丁版本、操作系统权限、WAL 状态、扩展和本机配置。跨电脑直接复制容易导致服务无法启动或产生不可验证状态。P1-1 使用逻辑备份，使目标数据库可独立创建并审计恢复过程。

## 全新电脑初始化

```powershell
Copy-Item platform/.env.example platform/.env
# 修改 platform/.env 的 POSTGRES_PASSWORD
platform/scripts/bootstrap-new-machine.ps1
```

脚本启动 PostgreSQL 17.10、Redis 7.4.9，执行 Alembic，启动 API、Publisher、Worker 和前端并检查健康状态。

## 数据备份

```powershell
platform/scripts/backup-data.ps1
```

备份脚本先停止 API、Publisher、Worker 和前端，避免数据库元数据与 Artifact 文件跨时点不一致；随后生成：

```text
handoff-bundle/
├── database.dump
├── artifact-store.zip
├── backup-manifest.json
├── RESTORE.md
└── checksums（记录在 backup-manifest.json）
```

Manifest 记录格式版本、UTC 时间、Git commit、Alembic revision、镜像版本、数据库名、每张业务表的行数、Artifact Store 文件数/总字节数和三个交接文件的 SHA-256。即使 Artifact Store 为空，也会产生合法 ZIP。脚本结束后恢复原服务。

## 安全恢复

```powershell
platform/scripts/restore-data.ps1 -BundleDirectory <handoff-bundle>
```

默认目标为 `thesis_platform_restored`。恢复程序：

1. 校验交接包全部 Hash；
2. 若目标数据库已存在则立即拒绝；
3. 若 Artifact 目标非空则立即拒绝；
4. 创建全新数据库；
5. 使用 `pg_restore --no-owner --no-acl --exit-on-error`；
6. 执行 Alembic 前向升级；
7. 解压 Artifact Store；
8. 将每张表行数、Artifact 文件数和总字节数与备份 Manifest 对照；
9. 对每个 `ArtifactVersion` 重新计算文件 SHA-256 和大小；
10. 终止旧电脑留下的活跃 Lease；
11. 通过恢复协调器重新生成可恢复 Outbox；
12. 输出新的数据库名，但不自动切换 `.env`。

只有人工核验完成后才修改 `DATABASE_URL` 指向恢复数据库。旧数据库不会被覆盖。

## Redis 为什么不迁移

Redis Stream 只保存工作通知；Task、NodeRun、Attempt、Lease、Outbox 和 ArtifactVersion 均在 PostgreSQL。换电脑导致 Redis 清空时：

- PENDING Outbox 会重新发布；
- RUNNING 节点的旧 Lease 被标记过期；
- 可重试节点生成新的 Outbox；
- 已成功节点通过执行指纹幂等跳过重复消息。

因此不复制 Redis RDB/AOF，也不把 Redis 当作业务事实备份。

## 离线 Docker 镜像

有网络时 Compose 自动拉取固定版本。无网络时在联网电脑执行：

```powershell
docker pull postgres:17.10-alpine
docker pull redis:7.4.9-alpine
docker compose -f platform/deploy/docker-compose.yml build
docker save -o p1-1-images.tar postgres:17.10-alpine redis:7.4.9-alpine thesis-platform-api thesis-platform-frontend
```

新电脑执行：

```powershell
docker load -i p1-1-images.tar
```

正式交接记录验收机的镜像 digest，而不只记录 tag。

## 新电脑验收

新电脑已有 Python/Node 时可以运行宿主机测试；推荐仍使用隔离的 Docker 验收，避免本机依赖差异：

```powershell
platform/scripts/bootstrap-new-machine.ps1
platform/scripts/test-all.ps1 -Docker -E2E
```

Docker 验收使用独立 `thesis_platform_test`，不会把测试用例的清表动作作用到正式数据库。E2E 使用真实 `thesis_platform` 创建一条可审计任务记录与 10 个 ArtifactVersion。

## 恢复后验证清单

- Alembic revision 与代码一致；
- Task、WorkflowRun、NodeRun、Attempt、ArtifactVersion 数量符合备份 Manifest；
- 所有 ArtifactVersion 相对路径位于 Artifact Store 内；
- 每个 Artifact 文件 SHA-256 与数据库一致；
- 没有跨机器绝对路径作为产物身份；
- 没有永久 RUNNING 的过期 Lease；
- PENDING/RETRYING 节点能够恢复投递；
- 已成功节点不会产生重复当前产物。
