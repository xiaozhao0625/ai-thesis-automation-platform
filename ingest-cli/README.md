# Ingest CLI v0.1-Prototype

资料摄取治理契约的离线参考实现。当前版本只面向单个论文任务的受控小样本，验证路径身份、预检处置、SHA-256、去重、角色建议、候选边界、敏感标记、Manifest、校验与断点恢复。

本原型不会扫描或导入历史论文库，不提供 FastAPI、PostgreSQL、Redis、Worker、权限系统或完整脱敏能力，也不会修改或删除源文件。

## 环境

- Python 3.11 或更高版本
- 运行依赖：`jsonschema`
- 测试依赖：`pytest`

在本目录执行：

```powershell
python -m pip install -e ".[test]"
```

## 扫描

准备一份符合冻结 `IngestConfig` 契约的配置后执行：

```powershell
python -m thesis_ingest scan `
  --config ingest-config.json `
  --output ingest-output/
```

`--output` 必须与配置中的 `output.output_directory` 指向同一目录。输出目录不得位于源挂载根内；非空目标目录不会被覆盖。标准命令会自动查找配置 Hash、规则版本和路径规范版本均匹配的 Checkpoint，并在确认已处理源文件未变化后继续扫描。

成功后恰好发布以下 10 个文件：

```text
ingest-manifest.json
source-mounts.json
artifacts.jsonl
excluded-items.jsonl
duplicate-groups.jsonl
primary-candidates.jsonl
reference-candidates.jsonl
sensitive-items.jsonl
ingest-issues.jsonl
summary.json
```

## 校验

在全新目录或文件传输后，可独立校验 Schema、文件 Hash、计数等式和跨记录引用：

```powershell
python -m thesis_ingest verify `
  --manifest ingest-output/ingest-manifest.json
```

## 退出码

| 退出码 | 含义 |
| ---: | --- |
| 0 | 成功 |
| 2 | 配置或命令输出目录不一致 |
| 3 | 源挂载、路径边界或续扫期间源变化错误 |
| 4 | 扫描被中断且已保留 Checkpoint |
| 5 | 输出包校验失败 |
| 10 | 其他流水线或内部错误 |

## 受控测试夹具

仓库提供一个确定性生成器，只生成 128 个合成文件；其中 EXE/DLL 是不可执行的文本标记，不含真实凭证、个人数据或历史论文：

```powershell
python tests/fixtures/build_controlled_sample.py .work/controlled-small-sample
```

配置示例见 `examples/controlled-small-sample/ingest-config.example.json`。替换其中的本地 `file:` URI 后即可扫描。

## 验收测试

```powershell
python -m pytest -q
python -m pytest -m recovery -q
python -m pytest -m security -q
```

正式契约快照位于 `contracts/v0.1/`，并由 `contract-lock.json` 逐字节锁定；规则位于 `rules/v0.1/`，由 `rule-lock.json` 锁定。若正式契约需要调整，应发布增量版本，不回改冻结的 v0.1 契约包。
