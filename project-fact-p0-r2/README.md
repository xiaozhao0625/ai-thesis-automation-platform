# ProjectFact P0 闭环修复候选 r2

候选标识：`v0.3.2-P0-r2` / `v1.2.4-P0-r2`  
状态：复审候选，未冻结，未发布  
Python 依赖：仅标准库

本目录只修复 ProjectFact 五个 P0，不编制六份实施级技术文档，不扩展页面，也不进入全量开发。

## 内容

- `fixtures/`：DOCX、Python、XLSX、PNG + 冻结 OCR、冲突源码及预期结果。
- `project_fact_r2/extractor.py`：四类真实输入提取和结构化定位。
- `project_fact_r2/governance.py`：型号分级、冲突、版本、快照、依赖传播和执行指纹。
- `schemas/`：ProjectFact、Version、Snapshot、Conflict、FactSourceLink、Locator、FactDependency、Alias 和检索分类 Schema。
- `tests/`：真实提取、负向型号、冲突传播、版本快照和 Schema 约束测试。
- `../uiux-prototype/project-fact-r2.json`：由本模块生成、供现有原型 API 使用的数据。

## 重建

```powershell
python tools\build_fixtures.py
python -m project_fact_r2.cli build-review-payload --fixtures fixtures --output ..\uiux-prototype\project-fact-r2.json
python -m unittest discover -s tests -v
```

随后在 `../uiux-prototype` 运行：

```powershell
node prototype.contract.test.mjs
$env:NODE_PATH=Join-Path (Join-Path $env:TEMP 'codex-playwright-check') 'node_modules'
node --test prototype.interaction.test.cjs
```

## 冻结约束

`68c5c50` 是评审失败候选，只供追溯。本候选必须专项复审通过后才能决定正式冻结提交；当前文件不得被描述为已发布的 v0.3.2 或 v1.2.4。
