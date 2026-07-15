# Ingest CLI v0.1-Prototype 实施计划

- 状态：APPROVED_FOR_IMPLEMENTATION
- 日期：2026-07-15
- 开发分支：`feat/ingest-cli-v0.1`
- 基线提交：`8d0e9fa`
- 设计提交：`8afd017`
- 设计规格：`docs/superpowers/specs/2026-07-15-ingest-cli-v0.1-prototype-design.md`

## 1. 执行原则

1. 正式 v0.1 契约包和提交 `8d0e9fa` 保持只读。
2. 在独立工作树和仓库内新目录 `ingest-cli/` 开发。
3. 每项生产行为遵循 RED → GREEN → REFACTOR：先写最小失败测试并确认失败原因，再写最小实现。
4. 每阶段结束运行该阶段测试；最终运行全量单元、集成、契约、恢复和安全验收。
5. 首轮只处理受控小样本，不扫描或导入历史论文库。
6. 源材料只读；任何输出均写入输出暂存区或测试临时目录。

## 2. 里程碑与 TDD 顺序

### M0：隔离环境与冻结基线

交付：

- 独立工作树 `.worktrees/ingest-cli-v0.1`；
- 设计状态 `APPROVED`；
- 本实施计划；
- 冻结契约校验基线记录。

验证：

- 工作树分支为 `feat/ingest-cli-v0.1`；
- 工作树无无关改动；
- 冻结包校验仍为 188 项通过；
- `8d0e9fa` 可达且内容未被回改。

### M1：Python 包、契约快照、规则锁与规范 JSON

先写测试：

- 包可通过 `python -m thesis_ingest --help` 加载；
- 四个 Schema 快照与冻结包逐字节相同；
- `contract-lock.json` 中 SHA-256 与文件一致；
- 配置与锁文件的契约/规则版本不一致时拒绝；
- 规范 JSON 对键顺序、Unicode、数字和转义产生稳定字节；
- 重复键、NaN、Infinity 被拒绝；
- JSON Schema 校验错误保留 JSON Pointer。

再实现：

- `pyproject.toml` 与 `src/thesis_ingest` 包骨架；
- `contracts.py`、`canonical_json.py`、`config.py`；
- 四 Schema 只读快照及两类 lock；
- 最小 `scan` / `verify` 命令解析。

阶段命令：

```powershell
python -m pytest tests/unit/test_canonical_json.py tests/contract/test_contract_snapshot.py tests/unit/test_config.py -q
```

### M2：SourceMount、路径安全、身份与目录发现

先写测试：

- 仅接受 `LOCAL_DIRECTORY` 与本地 file URI；
- 绝对 `relative_path`、盘符、UNC 和 `..` 越界被拒绝；
- 路径分隔符规范为 `/`；
- Unicode 归一化和大小写策略由挂载配置决定；
- Unicode/大小写碰撞进入隔离；
- 更换 `root_uri` 后 `source_occurrence_key` 不变；
- 输出目录位于挂载根内时拒绝启动；
- 符号链接不跟随；
- 发现顺序稳定且可重复；
- `.venv`、`node_modules`、`.git` 等目录可在遍历期剪枝并保留审计计数。

再实现：

- `paths.py`：挂载解析、规范相对路径、安全边界、稳定标识；
- `discovery.py`：确定性遍历、碰撞检测、目录剪枝；
- 对挂载根只读取元数据，不修改源文件。

阶段命令：

```powershell
python -m pytest tests/unit/test_paths.py tests/unit/test_discovery.py tests/integration/test_root_migration.py -q
```

### M3：预检、Hash、处置状态与审计问题

先写测试：

- 每个发现文件只有一个主处置；
- `.venv`、缓存、构建产物和第三方依赖被排除；
- EXE、DLL、脚本、数据库转储、凭证风险和可疑压缩包被隔离；
- 普通源码被接受；
- 低置信分类可转为 `NEEDS_REVIEW`；
- SHA-256 流式读取；
- Hash 前后大小或修改时间变化时不生成内容身份；
- Hash 失败仍生成可审计 issue；
- 原文件内容和元数据不被 CLI 修改。

再实现：

- `issues.py`：稳定错误码和问题记录；
- `preflight.py`：有序、互斥的处置规则；
- `hashing.py`：流式 Hash 与前后稳定性复核；
- 明确 `ACCEPTED / EXCLUDED / QUARANTINED / DUPLICATE / NEEDS_REVIEW` 状态机。

阶段命令：

```powershell
python -m pytest tests/unit/test_preflight.py tests/unit/test_hashing.py tests/integration/test_source_immutability.py -q
```

### M4：ArtifactRole、敏感分类与去重

先写测试：

- 角色建议只产生 `PROPOSED` 和 `AUTOMATED_SUGGESTION`；
- CLI 不产生 `HUMAN_CONFIRMED` 或 `VERIFIED_REFERENCE`；
- 扩展名独立判断的置信度不超过 0.70；
- 置信度低于 0.60 时进入人工复核；
- 数据手册、依赖包 PDF 和旧论文不成为当前正文主候选；
- 人脸图片、个人信息、问卷、访谈、数据库转储、凭证、源码、视频和音频得到可解释标记；
- 同 Hash 多路径形成 DuplicateGroup 且保留所有 occurrence；
- 规范代表优先且必须为 `ACCEPTED + parser_eligible`；
- 无合格规范代表时明确记录，不以排除项或第三方依赖替代。

再实现：

- `classification.py`：20 项冻结角色建议与理由；
- `sensitivity.py`：四级数据分类及模型使用限制建议；
- `deduplication.py`：Hash 分组、规范代表排序和审计字段。

阶段命令：

```powershell
python -m pytest tests/unit/test_classification.py tests/unit/test_sensitivity.py tests/unit/test_deduplication.py -q
```

### M5：主版本候选、工程根候选与参考文献候选

先写测试：

- 正文候选评分严格采用批准规格权重；
- 工程根候选锚点优先级和评分严格采用批准规格；
- top ≥ 0.70 且差值 > 0.05 时唯一推荐；
- top ≥ 0.70 且差值 ≤ 0.05 时并列待确认；
- 最高分 < 0.70 时无推荐；
- 备份、第三方依赖、构建产物和旧论文不能自动成为主版本；
- 无可观察候选时不伪造 ID，并记录 `PROJECT_SCOPE_UNRESOLVED`；
- 裸 TXT 引用只生成 `UNVERIFIED ReferenceCandidate`；
- 不生成 EvidenceChunk、Claim 或 VerifiedReference；
- Imported EngineeringResult 不能携带可信成功结论。

再实现：

- `candidates.py`：正文和工程候选评分；
- `references.py`：引用线索提取与未核验候选；
- EngineeringResult 输入边界和 Schema 契约测试。

阶段命令：

```powershell
python -m pytest tests/unit/test_candidates.py tests/unit/test_references.py tests/contract/test_engineering_result.py -q
```

### M6：JSON/JSONL 输出、Manifest、Verify 与原子发布

先写测试：

- 完整输出恰好包含冻结的 10 个文件；
- JSONL 每行完整、无重复键、可逐行 Schema 校验；
- 五类处置计数等式成立；
- 所有引用 ID 可解析；
- Manifest 的 output_hashes 与实际文件匹配；
- 篡改任一候选输出后 `verify` 退出码为 5；
- 目标目录非空时拒绝覆盖；
- `COMPLETED` 仅在全部输出落盘、校验和 Hash 完成后发布；
- `PARTIAL` 不得伪装为 `COMPLETED`；
- 发布使用同卷目录重命名，不逐文件暴露半成品。

再实现：

- `output.py`：JSON/JSONL 写入、Hash、关系校验、同卷发布；
- `verification.py`：独立离线校验；
- Manifest 和 summary 汇总；
- 稳定退出码 0/2/3/4/5/10。

阶段命令：

```powershell
python -m pytest tests/unit/test_output.py tests/integration/test_manifest.py tests/integration/test_verify.py -q
```

### M7：Checkpoint、恢复与端到端流水线

先写测试：

- 中断后从最后已确认批次恢复；
- 已写 JSONL 不丢行、不重复；
- 恢复时复核此前源文件大小、mtime 和 Hash；
- 恢复期间源文件变化会拒绝旧内容身份；
- checkpoint 版本或规则版本不匹配时拒绝恢复；
- publish 前中断不会暴露 `COMPLETED`；
- 进程再次执行可在原 staging scan 内恢复；
- 全新输出目录可独立 `verify`。

再实现：

- `checkpoint.py`：版本化 checkpoint 与批次游标；
- `pipeline.py`：阶段编排、状态转换、恢复；
- `cli.py`：scan/verify 命令、错误映射和人类可读摘要。

阶段命令：

```powershell
python -m pytest tests/integration/test_resume.py tests/integration/test_pipeline.py tests/integration/test_cli.py -q
```

### M8：固定 128 文件夹具与验收矩阵

先写测试：

- 夹具生成器两次生成的逻辑内容和预期清单相同；
- 固定文件数为 128；
- 夹具只含合成内容和可再分发公开快照；
- EXE/DLL 仅含安全魔数或文本占位，不包含可执行逻辑；
- 夹具覆盖重复、碰撞、备份、多个最终版、噪声、敏感标记、引用线索和错误输入。

再实现：

- `tests/fixtures/build_controlled_sample.py`；
- `examples/controlled-small-sample/` 配置与说明；
- 单元与契约测试总数不少于 80；
- 故障恢复场景不少于 6；
- 负向安全场景不少于 12。

阶段命令：

```powershell
python -m pytest -q
```

## 3. 最终验收命令

```powershell
# CLI 包全量测试
python -m pytest -q

# 冻结正式契约包回归
python docs/ingest-governance-v0.1/tests/validate_contract.py --package <正式契约包绝对路径>

# 受控小样本端到端
python -m thesis_ingest scan --config <临时配置绝对路径> --output <临时输出绝对路径>
python -m thesis_ingest verify --manifest <临时输出>/ingest-manifest.json

# 仓库状态与冻结提交审计
git status --short
git diff 8d0e9fa -- <冻结包路径>
```

最终报告必须给出实际测试数量、恢复场景数、安全负向场景数、Schema 校验结果、端到端退出码及未完成项。未获得新授权前不推送、不合并、不创建 FastAPI/PostgreSQL/Redis/Worker。

## 4. 提交边界

建议使用小步提交：

1. `docs: approve ingest cli implementation plan`
2. `test: specify ingest config and canonical json` + 对应最小实现提交
3. `feat: add source mount identity and discovery`
4. `feat: add preflight hashing and decisions`
5. `feat: add artifact classification and deduplication`
6. `feat: add primary and reference candidates`
7. `feat: add manifest output verification and resume`
8. `test: add controlled ingest acceptance fixture`
9. `docs: record ingest cli prototype verification`

每个提交前必须运行与其范围相符的测试；最终提交前必须运行第 3 节全部验收。
