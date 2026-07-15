# r1 → r2 变更矩阵

| 专项项 | `68c5c50` 失败候选 | P0-r2 候选 |
| --- | --- | --- |
| 输入 | HTML 固定数组 | DOCX、Python、XLSX、PNG/OCR 冻结夹具 |
| 定位 | 文件名和简短文字 | ArtifactVersion + 来源专属坐标 + excerpt Hash |
| 精确型号 | 固定标签 | Schema oneOf + 运行时非法组合拒绝 |
| 冲突对象 | DOM 区块 | ProjectFactConflict + 两侧 FactSourceLink |
| 阻断 | 两个节点状态修改 | FactDependency 闭包和状态转换表 |
| 失效 | 固定节点数组 | NodeRun、Claim、Artifact、质量、交付选择性传播 |
| 快照 | 前端整数加一 | ProjectFactVersion、Snapshot、SHA-256 Hash |
| 指纹 | 无 | Snapshot Hash + FactVersion IDs + target ID |
| 目录 | 直接回到 PENDING_APPROVAL | 旧 NodeRun INVALIDATED，新 NodeRun READY |
| 页面 | 冲突期间正文仍显示一致 | 冲突/确认后相关内容统一 INVALIDATED |
| 测试 | 固定正向 13/13 | 28 条 Python 提取/负向/依赖测试 + 13 条浏览器回归 |
