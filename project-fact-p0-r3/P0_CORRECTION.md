# ProjectFact P0-r3 最小修复说明

## P0-1 真实启动确认

- 初始提取只创建 `PROPOSED` ProjectFact；`current_fact_version_id` 为 `null`，不存在 ACTIVE Snapshot。
- `POST /api/project-facts/confirm-intake` 才创建锁定的 ProjectFactVersion、ACTIVE ProjectFactSnapshot、Snapshot Hash、HumanApproval 和审计事件。
- 前端点击不再自行把事实改成 `LOCKED`，而是消费确认接口返回的对象。

## P0-2 全具体型号机器保护

- 从当前 Snapshot 中动态收集所有 `HARDWARE_MODEL` 与 `MODULE_MODEL`。
- 型号替换检查不再只扫描 STM32；当前夹具覆盖 STM32F103C8T6、DHT11、ESP8266-01S 与 SSD1306。
- DHT11 → DHT22、ESP8266-01S → ESP32、SSD1306 → SSD1309 均产生 `FACT_CONSTRAINT_VIOLATION / BLOCKING`。
- `BACKGROUND_ONLY`、`COMPARISON_ONLY` 与 `GENERAL_PRINCIPLE` 明确语境仍允许相关型号出现。

## P0-3 运行时检索约束

- `validate_retrieval_classification()` 同时验证 `evidence_role`、`supports_project_fact`、`supports_model_parameters` 与 `alias_scope`。
- 非精确型号的支持布尔值必须为 `false`；确认别名必须有合法 `alias_scope`，型号参数证据仅允许 `PROJECT_FACT_AND_PARAMETERS`。

## P0-4 自包含复审包

- 再生测试优先定位 `../prototype/project-fact-r3.json`，源码工作区再回退到 `../uiux-prototype/project-fact-r3.json`。
- 解压后的复审包无需软链接或手工改路径，即可复现候选测试。
