# UI/UX v1.2.4-P0-r2 测试结果

执行日期：2026-07-15

## 静态契约

`node prototype.contract.test.mjs`：通过。

检查范围：20 个页面/检查器视图、v1.2.1 关键交互目标、8 阶段真实业务边、ProjectFact API、禁止 HTML 硬编码、检索准入分级、事实快照、依赖传播、SVG 端口边、TaskSubNavigation、页面级 Query 白名单、全局路由和 History API。

## ProjectFact 可执行测试

`python -m unittest discover -s tests -v`：28/28 通过。

覆盖真实 DOCX/Python/XLSX/PNG-OCR 提取、来源定位、输入变更、OCR Hash、非法型号证据组合、冲突实体、依赖闭包、选择性失效、版本快照、执行指纹和目录新旧 NodeRun。

## 浏览器交互

`node --test prototype.interaction.test.cjs`：13/13 通过，0 失败。

1. 目录确认后在原 DAG 节点位置失效，且无重复结果面板。
2. DeadLetter 恢复新建独立 QUEUED NodeRun 并保留来源。
3. 质量复检先显示 ReviewRun RUNNING，再令质量闸门成功。
4. 终稿审批定位 DeliveryPackage v3，批准后启用正式下载。
5. 8 阶段、12 节点按真实业务顺序连接；节点均在所属阶段内，SVG 边端点均在端口容差内。
6. 前置章节组展开显示第 1—5 章五个节点，NodeRun 不重复。
7. 九项任务导航、浏览器后退/前进、刷新和深链接状态正确。
8. 非工作流页面会清除无关 `node/attempt`，并保持各自允许的 Query；Workflow Inspector 不跨页泄漏。
9. 工作台、任务、审批、基准、模板和系统页面均同步更新页面、URL 与 History 状态。
10. 启动闸门①确认 API 返回的 ProjectFact，并显示四类来源定位。
11. `ProjectFactSnapshot v5` 在材料、目录、内容、BOM 和质量页面保持一致。
12. 检索结果区分 `EXACT_MODEL`、`SERIES_MATCH` 和 `RELATED_MODEL`，相关型号只能使用 `COMPARISON_ONLY`。
13. 冲突按依赖闭包处理 NodeRun、Claim、Artifact、质量和交付；确认前展示影响范围，确认后旧目录失效、新目录 NodeRun 为 READY。

## 视觉检查

已在 1440×900 浏览器视口复核项目与材料默认态、冲突态和影响确认弹窗。来源定位、候选值、影响数量和确认按钮无重叠；右栏可独立滚动，控制台无错误。

本结果只支持提交 `v0.3.2-P0-r2 / v1.2.4-P0-r2` 专项复审候选，不代表正式冻结。
