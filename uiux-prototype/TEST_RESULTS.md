# UI/UX v1.2.3 测试结果

执行日期：2026-07-15

## 静态契约

`node prototype.contract.test.mjs`：通过。

检查范围：20 个页面/检查器视图、v1.2.1 关键交互目标、8 阶段真实业务边、工程绿 Token、Attempt 2/3、修订轮次 2/2、ApprovalBar 88px 安全区、SVG 画布、端口边、TaskSubNavigation、页面级 Query 白名单、全局路由映射、History API 与章节组控制。

## 浏览器交互

`node --test prototype.interaction.test.cjs`：9/9 通过，0 失败。

1. 目录确认后在原 DAG 节点位置失效，且无重复结果面板。
2. DeadLetter 恢复新建独立 QUEUED NodeRun 并保留来源。
3. 质量复检先显示 ReviewRun RUNNING，再令质量闸门成功。
4. 终稿审批定位 DeliveryPackage v3，批准后启用正式下载。
5. 8 阶段、11 节点按真实业务顺序连接；节点均在所属阶段内，SVG 边端点均在端口容差内。
6. 前置章节组展开显示第 1—5 章五个节点，NodeRun 不重复。
7. 九项任务导航、浏览器后退/前进、刷新和深链接状态正确。
8. 非工作流页面会清除无关 `node/attempt`，并保持各自允许的 Query；Workflow Inspector 不跨页泄漏。
9. 工作台、任务、审批、基准、模板和系统页面均同步更新页面、URL 与 History 状态。

## 视觉检查

已在 1440×900 浏览器视口复核工作流初始状态和 60% 适配画布状态。8 个阶段、11 个节点和同阶段竖向端口连线均完整显示，未发现节点越界、重复或文字遮挡。

本轮只校正 UI/UX 原型语义与路由；DOCX 像素级复审结论沿用 v1.2.2 正式复审记录。
