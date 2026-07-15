# ProjectFact P0-r3 测试结果

日期：2026-07-15  
候选：`v0.3.2-P0-r3` / `v1.2.4-P0-r3`

## 当前结果

- Python 标准库单元测试：34/34 通过。
- UI 静态契约：通过。
- Playwright/Chrome 浏览器测试：13/13 通过。

## r3 新增负向与接口覆盖

- 初始 API 返回 `PROPOSED` 事实、空 FactVersion 和空 ACTIVE Snapshot；启动确认后返回 FactVersion、Snapshot Hash、HumanApproval 与审计事件。
- Snapshot 动态保护 STM32F103C8T6、DHT11、ESP8266-01S 与 SSD1306。
- DHT11 → DHT22、ESP8266-01S → ESP32、SSD1306 → SSD1309 均为 `BLOCKING`。
- `RELATED_MODEL`、`SERIES_MATCH`、`CONFLICTING_MODEL` 伪造支持布尔标志均被运行时拒绝；确认别名的 `alias_scope` 也受运行时约束。
- 包内测试在 `prototype/` 结构下定位 payload，不依赖源码仓库目录名。

本结果只支持 r3 进入专项复审，不代表冻结、发布或推送。
