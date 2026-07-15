# ProjectFact P0-r2 测试结果

日期：2026-07-15  
候选：`v0.3.2-P0-r2` / `v1.2.4-P0-r2`

## 当前结果

- Python 标准库单元测试：28/28 通过。
- UI 静态契约：通过。
- Playwright/Chrome 浏览器测试：13/13 通过。

## 关键负向覆盖

- 修改源码型号后，提取值和 ArtifactVersion ID 同时变化。
- 删除输入不会被静默忽略；OCR 图片或文本 Hash 不一致会失败。
- `RELATED_MODEL + PROJECT_FACT_EVIDENCE` 在 Schema 分支和运行时均被拒绝。
- 正文、BOM、参数表、图表、测试章节、摘要和总结中的非锁定型号会产生阻断问题；明确比较语境允许相关型号。
- 主控型号冲突后，已完成依赖失效、未执行依赖阻断、运行中节点请求取消、无关节点保持不变。
- 下游对象由冻结依赖图 BFS 计算；删除依赖边后，对应节点保持有效且不会被误伤。
- Claim、检索 Artifact、质量报告和交付包均进入选择性失效范围。
- 确认后生成新 ProjectFactVersion、不同 Snapshot Hash 和不同 execution fingerprint。
- 旧 outline NodeRun 保持 INVALIDATED，新 outline NodeRun 为 READY。
- 冲突期间正文不再显示“已锁定 / BOM 一致”，确认前展示真实影响范围。

本结果仅支持进入专项复审，不代表正式冻结。
