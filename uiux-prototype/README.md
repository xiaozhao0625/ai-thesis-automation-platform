# UI/UX v1.2.4-P0-r2 复审候选

这是 ProjectFact 五项 P0 的受控修复候选，不是已冻结的 v1.2.4。页面通过本地 API 消费 `../project-fact-p0-r2/` 从冻结夹具生成的事实、冲突、依赖传播和版本快照数据。

## 本版范围

- 数据驱动、只读的 HTML 节点层 + SVG 边层 DAG 画布。
- 232px 最小阶段列、180px 节点、横向滚动、空白区拖动、60%—160% 缩放和适配画布。
- 真实业务顺序：前置章节（第 1—5 章）→ 工程验证 → 第 6 章 → 第 7 章 → 整稿质量检查 → 质量闸门 → DOCX 渲染 → 终稿审批。
- 准备阶段包含“事实确认与锁定”，事实来自 DOCX、Python、XLSX 和 PNG/OCR 冻结夹具。
- 完整型号按不同对象处理；检索分为 `EXACT_MODEL`、`CONFIRMED_ALIAS`、`SERIES_MATCH`、`RELATED_MODEL` 和 `CONFLICTING_MODEL`。
- 新建任务、总览、材料、目录、内容、证据、质量和交付在冲突期间使用同一事实状态。
- 用户材料冲突创建 `ProjectFactConflict`；FactDependency 闭包决定 `INVALIDATED / BLOCKED / CANCEL_REQUESTED / 保持有效`。
- 人工确认前展示真实影响范围；确认后创建 ProjectFactVersion v3、Snapshot v6、新执行指纹和 READY 的新目录 NodeRun。
- 目录修改后的 INVALIDATED 原位切换、前置章节组折叠/展开及无重复 NodeRun 约束。
- 九项统一 TaskSubNavigation、页面级 Query 白名单、检查器隔离、History API、刷新和深链接恢复。
- 工作台、任务列表、审批、基准、模板及三个系统页面均具备正式 URL 和 History 状态。
- 保留 v1.2.1 的目录失效、DeadLetter 恢复、质量复检和终稿审批闭环。

可执行 P0 候选位于 `../project-fact-p0-r2/`。`68c5c50` 继续作为失败候选追溯点，不修改、不冻结、不推送。

## 本地预览

```powershell
node prototype.server.cjs
```

访问 `http://127.0.0.1:4173/tasks/task-001/materials`。预览服务同时提供 ProjectFact 候选 API 和 SPA 深链接回退。

## 本地验证

```powershell
Push-Location ..\project-fact-p0-r2
python -m unittest discover -s tests -v
Pop-Location

node prototype.contract.test.mjs

$env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD='1'
$prefix=Join-Path $env:TEMP 'codex-playwright-check'
& (Get-Command npm.cmd).Source install --prefix $prefix playwright@1.61.1
$env:NODE_PATH=Join-Path $prefix 'node_modules'
node --test prototype.interaction.test.cjs
```

浏览器测试使用本机 Chrome和原型 API 服务。若环境已提供 Playwright，只需保证 `NODE_PATH` 可解析 `playwright` 模块。
