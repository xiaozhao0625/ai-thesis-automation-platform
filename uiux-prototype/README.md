# UI/UX v1.2.3 可点击原型

这是 AI 论文自动化生产平台的前端实施原型，基于 v1.2.2 正式复审结论进行工作流语义与路由一致性校正。

## 本版范围

- 数据驱动、只读的 HTML 节点层 + SVG 边层 DAG 画布。
- 232px 最小阶段列、180px 节点、横向滚动、空白区拖动、60%—160% 缩放和适配画布。
- 真实业务顺序：前置章节（第 1—5 章）→ 工程验证 → 第 6 章 → 第 7 章 → 整稿质量检查 → 质量闸门 → DOCX 渲染 → 终稿审批。
- 目录修改后的 INVALIDATED 原位切换、前置章节组折叠/展开及无重复 NodeRun 约束。
- 九项统一 TaskSubNavigation、页面级 Query 白名单、检查器隔离、History API、刷新和深链接恢复。
- 工作台、任务列表、审批、基准、模板及三个系统页面均具备正式 URL 和 History 状态。
- 保留 v1.2.1 的目录失效、DeadLetter 恢复、质量复检和终稿审批闭环。

## 本地预览

```powershell
node prototype.server.cjs
```

访问 `http://127.0.0.1:4173/tasks/task-001/workflow`。预览服务会对深链接执行 SPA 回退。

## 本地验证

```powershell
node prototype.contract.test.mjs

$env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD='1'
$prefix=Join-Path $env:TEMP 'codex-playwright-check'
& (Get-Command npm.cmd).Source install --prefix $prefix playwright@1.61.1
$env:NODE_PATH=Join-Path $prefix 'node_modules'
node --test prototype.interaction.test.cjs
```

浏览器测试使用本机 Chrome；测试内置临时静态 HTTP 服务。若环境已提供 Playwright，只需保证 `NODE_PATH` 可解析 `playwright` 模块。
