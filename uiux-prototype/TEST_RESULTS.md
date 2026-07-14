# UI/UX v1.2.2 测试结果

执行日期：2026-07-15

## 静态契约

`node prototype.contract.test.mjs`：通过。

检查范围：15 个核心页面、v1.2.1 关键交互目标、工程绿 Token、Attempt 2/3、修订轮次 2/2、ApprovalBar 88px 安全区、SVG 画布、端口边、TaskSubNavigation、History API 与章节组控制。

## 浏览器交互

`node --test prototype.interaction.test.cjs`：7/7 通过，0 失败。

1. 目录确认后在原 DAG 节点位置失效，且无重复结果面板。
2. DeadLetter 恢复新建独立 QUEUED NodeRun 并保留来源。
3. 质量复检先显示 ReviewRun RUNNING，再令质量闸门成功。
4. 终稿审批定位 DeliveryPackage v3，批准后启用正式下载。
5. 节点均在所属阶段内，SVG 边端点均在端口容差内。
6. 章节组展开显示五个章节节点，NodeRun 不重复。
7. 九项任务导航、浏览器后退/前进、刷新和深链接状态正确。

## 视觉检查

已检查 1440px 工作流初始状态截图：`screenshots/workflow-1440-initial.png`。

整页截图在当前桌面环境中会使 Chrome 自动化进程超时，因此未将其作为验收依据；布局与交互由短时浏览器测试覆盖。DOCX 生成完成，但因当前环境没有可用 LibreOffice，未执行 DOCX→PNG 像素级渲染检查。
