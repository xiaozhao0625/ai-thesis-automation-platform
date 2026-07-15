# UI/UX v1.2.4 测试结果

执行日期：2026-07-15

## 静态契约

`node prototype.contract.test.mjs`：通过。

检查范围：20 个页面/检查器视图、v1.2.1 关键交互目标、8 阶段真实业务边、ProjectFact 事实闸门、精确型号、检索准入分级、事实快照、冲突阻断与失效传播、SVG 端口边、TaskSubNavigation、页面级 Query 白名单、全局路由映射和 History API。

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
10. 启动闸门①确认解析出的 ProjectFact，完整型号不被缩写或替换。
11. `ProjectFactSnapshot v5` 在材料、目录、内容、BOM 和质量页面保持一致。
12. 检索结果正确区分 `EXACT_MATCH`、`SERIES_MATCH` 和 `RELATED_MODEL`，相关型号只能用于比较。
13. 用户材料冲突生成 `PROJECT_FACT_CONFLICT` 并阻断目录；人工确认后生成 v6 快照，下游进入 `INVALIDATED`。

## 视觉检查

已在 1440×900 浏览器视口复核项目与材料默认/冲突状态及内容事实锁状态。六项事实、冲突处理、锁定标记和 BOM 均无越界或文字遮挡；页面允许右栏独立滚动，浏览器控制台无错误。

ProjectFact Schema 与三组验收夹具已在 v0.3.2 研发基线校正包中通过独立契约测试。DOCX 像素级复审结论沿用 v1.2.2 正式复审记录。
