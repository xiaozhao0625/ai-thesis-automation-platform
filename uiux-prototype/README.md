# UI/UX v1.2.2 可点击原型

这是 AI 论文自动化生产平台的前端实施原型，基于已通过的 v1.2.1 交互闭环进行 v1.2.2 工作流布局与任务导航校正。

## 本版范围

- 数据驱动、只读的 HTML 节点层 + SVG 边层 DAG 画布。
- 232px 最小阶段列、180px 节点、横向滚动、空白区拖动、60%—160% 缩放和适配画布。
- 目录修改后的 INVALIDATED 原位切换、章节组折叠/展开及无重复 NodeRun 约束。
- 九项统一 TaskSubNavigation、可点击面包屑、History API、刷新和深链接恢复。
- 保留 v1.2.1 的目录失效、DeadLetter 恢复、质量复检和终稿审批闭环。

## 本地验证

```powershell
$p='C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\.pnpm'
$env:NODE_PATH="$p\playwright@1.61.1\node_modules;$p\playwright-core@1.61.1\node_modules"
$node='C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
& $node prototype.contract.test.mjs
& $node --test prototype.interaction.test.cjs
```

浏览器测试使用本机 Chrome；测试内置临时静态 HTTP 服务，无需安装项目依赖。
