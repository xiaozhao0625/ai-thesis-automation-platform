# UI/UX v1.2.4-P0-r3 测试结果

执行日期：2026-07-15

## 静态契约

`node prototype.contract.test.mjs`：通过。

检查范围包含 20 个页面/检查器视图、v1.2.1 关键交互目标、8 阶段真实业务边、ProjectFact API、禁止 HTML 硬编码、启动确认、检索准入、事实快照、依赖传播、SVG 端口边、TaskSubNavigation、Query 白名单、全局路由和 History API。

## ProjectFact 可执行测试

`python -m unittest discover -s tests -v`：34/34 通过。

覆盖真实 DOCX/Python/XLSX/PNG-OCR 提取、来源定位、输入变更、OCR Hash、启动确认、完整型号负向替换、运行时证据支持标志、冲突实体、依赖闭包、选择性失效、版本快照、执行指纹与自包含包路径。

## 浏览器交互

`node --test prototype.interaction.test.cjs`：13/13 通过，0 失败。

启动闸门测试现在先验证 API 的 `PROPOSED` 状态、空 Snapshot 和空 FactVersion，再验证点击确认后由 API 返回 ACTIVE Snapshot、Hash、FactVersion、HumanApproval 与审计事件。其余 DAG、导航、Query 隔离、冲突闭包和新目录 READY 回归保持通过。

本结果只支持提交 `v0.3.2-P0-r3 / v1.2.4-P0-r3` 专项复审候选，不代表正式冻结、发布或推送。
