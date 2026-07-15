# ProjectFact P0-r2 校正说明

## P0-1 真实提取

- DOCX：读取 OOXML 段落，保存页码、章节、段落号和字符区间。
- Python：使用 AST 读取常量，保存 fixture commit、文件、起止行和符号名。
- XLSX：读取 OOXML 单元格，保存工作表和单元格地址。
- 图片：读取真实 PNG，校验图片 Hash、OCR 文本 Hash 和边界框后提取事实。
- 每条观察记录均包含 ArtifactVersion ID、原文、原文 Hash、置信度和 SourceLocator。

## P0-2 型号机器约束

- 匹配类型改为 `EXACT_MODEL | CONFIRMED_ALIAS | SERIES_MATCH | RELATED_MODEL | CONFLICTING_MODEL`。
- 证据角色改为 `PROJECT_FACT_EVIDENCE | MODEL_PARAMETER_EVIDENCE | GENERAL_PRINCIPLE | BACKGROUND_ONLY | COMPARISON_ONLY | REJECTED`。
- JSON Schema `oneOf` 与运行时校验同时拒绝 `RELATED_MODEL + PROJECT_FACT_EVIDENCE`。

## P0-3 依赖闭包

- FactDependency 连接 ProjectFactVersion 与 NodeRun、Claim、ArtifactVersion、QualityReport、DeliveryPackage；受影响集合由冻结依赖图 BFS 计算。
- `SUCCEEDED / WAITING_FOR_APPROVAL` 转 `INVALIDATED`。
- `READY / QUEUED / PENDING` 转 `BLOCKED`。
- `RUNNING` 转 `CANCEL_REQUESTED`，取消完成后为 `BLOCKED`。
- 无事实依赖的对象保持原状态。

## P0-4 不可变版本和快照

- 人工决定创建新的 ProjectFactVersion 和 ProjectFactSnapshot。
- Snapshot Hash 与 execution fingerprint 使用规范化 JSON 和 SHA-256。
- 旧版本、旧 Snapshot 和旧 NodeRun 保留。
- 旧 outline NodeRun 为 `INVALIDATED`；新 NodeRun 为 `READY`，重新执行完成后才能进入审批。

## P0-5 页面状态

- 不新增页面，仅更新新建任务、总览、材料、目录、正文、资料、质量和交付的事实状态。
- 冲突期间正文、BOM、检索证据、质量报告和交付包不再显示有效。
- 人工确认前展示失效、阻断、取消和保留对象；按钮文案明确为“确认事实并使受影响下游失效”。
