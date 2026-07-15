# ProjectFact P0 闭环修复候选 r3

候选标识：`v0.3.2-P0-r3` / `v1.2.4-P0-r3`  
状态：复审候选，未冻结、未发布、未推送  
Python 依赖：仅标准库

本目录只修复 r2 专项复审发现的四项 P0：真实启动确认、全具体型号保护、运行时检索约束和自包含包路径。未新增页面，未扩展其他功能，未编制六份实施级技术文档。

## 内容

- `fixtures/`：DOCX、Python、XLSX、PNG + 冻结 OCR、冲突源码及预期结果。
- `project_fact_r3/extractor.py`：四类真实输入提取和结构化定位。
- `project_fact_r3/governance.py`：启动确认、型号分级、运行时检索约束、冲突、快照、依赖传播和执行指纹。
- `schemas/`：ProjectFact、Version、Snapshot、Conflict、FactSourceLink、Locator、FactDependency、Alias 和检索分类 Schema。
- `tests/`：真实提取、负向型号、运行时支持标志、启动确认、冲突传播、版本快照和 Schema 约束测试。
- `../uiux-prototype/project-fact-r3.json`：由本模块生成、供原型 API 使用的数据。

## 重建

源码工作区：

```powershell
python -m project_fact_r3.cli build-review-payload --fixtures fixtures --output ..\uiux-prototype\project-fact-r3.json
python -m unittest discover -s tests -v
```

自包含复审包中，默认使用相邻的 `../prototype/`：

```powershell
python -m project_fact_r3.cli build-review-payload --fixtures fixtures --output ..\prototype\project-fact-r3.json
python -m unittest discover -s tests -v
```

随后在 `../uiux-prototype` 运行：

```powershell
node prototype.contract.test.mjs
$env:NODE_PATH=Join-Path (Join-Path $env:TEMP 'codex-playwright-check') 'node_modules'
node --test prototype.interaction.test.cjs
```

## 候选约束

`68c5c50` 与 `91e1b51` 都是评审失败候选，只供追溯。本候选必须经下一轮专项复审通过后，才可决定是否冻结正式 `v0.3.2 / v1.2.4`；当前文件不得被描述为正式发布版本。
