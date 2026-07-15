# Ingest CLI v0.1-Prototype 实现设计

- 状态：APPROVED
- 阶段：P0-1 资料摄取 CLI 最小闭环
- 日期：2026-07-15
- 开发分支：feat/ingest-cli-v0.1
- 基线提交：8d0e9fa
- 契约版本：资料摄取、来源治理与工程结果统一模型 v0.1
- 正式基线位置：项目根目录 05_研发基线与PRD文档_20260714/v0.1_资料摄取来源治理与工程结果统一模型

## 1. 目标与边界

本阶段实现一条可独立验收的 Python CLI 资料摄取最小闭环。CLI 面向单个论文任务的受控材料包、V1.0 标准基准项目、固定公开资料快照和少量代表性测试数据，不面向历史论文库全量导入。

CLI 必须证明以下规则能够在无 Web、API、数据库、Redis、Worker、登录和权限系统的条件下独立运行：

- SourceMount 与可迁移相对路径；
- 目录发现、预检、逻辑隔离和唯一主处置；
- 流式 SHA-256、文件稳定性复核和精确去重；
- ArtifactRole 自动建议；
- 正文与工程主版本候选；
- 参考文献候选准入；
- 敏感资料分类建议；
- JSON/JSONL 分批写出；
- Manifest、Checkpoint、恢复和独立 Verify。

本阶段明确不包含：

- FastAPI、PostgreSQL、Redis、Worker、对象存储或 UI；
- 完整权限、DLP、自动脱敏或密钥管理；
- 真实人脸识别模型；
- EvidenceChunk、Claim、正式引用或 VerifiedReference；
- 自动人工确认、ProjectFact 正式锁定或正式主版本选择；
- 15 万历史论文文件扫描、复制或导入；
- 修改、删除、移动、执行或解压源文件；
- 修改冻结的 v0.1 正式基线和 8d0e9fa。

若实现发现冻结契约必须调整，只能新增 v0.1.1 增量设计和 Schema，不得回改 v0.1。

## 2. 方案选择

### 2.1 采用方案

采用“标准库优先的模块化 CLI”：

- Python 3.11 及以上；
- argparse、pathlib、hashlib、json、os、stat、mimetypes、zipfile、unicodedata 等标准库；
- jsonschema 是唯一正式运行时第三方依赖；
- pytest 是测试依赖；
- JSON Schema 是输出数据的唯一结构权威；
- Python dataclass 只表达扫描期内部状态，不复制正式 Schema。

内部提供专用 canonical_json 模块，实现冻结值域所需的 RFC 8785 JCS 序列化，并以规范向量覆盖字符串、Unicode、对象键排序、数组、整数、有限小数、布尔值和 null。NaN、Infinity、重复键和无法规范化的数值一律拒绝。

### 2.2 排除方案

Typer + Pydantic 未采用，因为它会形成第二套公开模型和校验语义，增加与冻结 JSON Schema 漂移的风险。

单文件扫描脚本未采用，因为它无法清晰承载分批写出、恢复、独立 Verify、80 条以上测试和未来 Worker 复用。

## 3. 仓库与目录

所有实现位于新的 ingest-cli 目录：

~~~text
ingest-cli/
├── pyproject.toml
├── README.md
├── contracts/
│   └── v0.1/
│       ├── contract-lock.json
│       ├── source-mount.schema.json
│       ├── ingest-manifest.schema.json
│       ├── artifact-ingest-record.schema.json
│       └── engineering-result.schema.json
├── rules/
│   └── v0.1/
│       ├── rule-lock.json
│       ├── ingest-rules.json
│       ├── artifact-classification.json
│       └── candidate-scoring.json
├── src/
│   └── thesis_ingest/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config.py
│       ├── contracts.py
│       ├── canonical_json.py
│       ├── paths.py
│       ├── discovery.py
│       ├── preflight.py
│       ├── hashing.py
│       ├── classification.py
│       ├── deduplication.py
│       ├── candidates.py
│       ├── references.py
│       ├── sensitivity.py
│       ├── checkpoint.py
│       ├── output.py
│       ├── verification.py
│       ├── issues.py
│       └── pipeline.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── fixtures/
└── examples/
    └── controlled-small-sample/
~~~

contracts/v0.1 中的四个 Schema 是正式基线的原字节快照。contract-lock.json 记录文件名、SHA-256、契约版本和来源提交。测试必须证明快照 Hash 未变化；实现不得在运行时修改这些文件。

rules/v0.1 保存本原型的确定性规则数据。rule-lock.json 记录三个规则文件的 SHA-256，文件内版本必须与 IngestConfig 的 rule_set_version 和 capability_pack.classification_rule_version 一致。规则修改必须提升规则版本并产生新快照，禁止同版本静默改权重。

## 4. 命令契约

首轮支持：

~~~powershell
python -m thesis_ingest scan --config ingest-config.json --output ingest-output/
python -m thesis_ingest verify --manifest ingest-output/ingest-manifest.json
~~~

scan 的 --output 与配置 output.output_directory 必须解析到同一目录，否则以退出码 2 拒绝启动，不存在静默覆盖优先级。

配置中的 output_directory 相对 ingest-config.json 所在目录解析；命令行 --output 相对当前进程工作目录解析。两者执行绝对化、符号链接/重解析点安全检查和大小写策略归一化后必须指向同一位置。首轮 SourceMount 只支持 mount_type=LOCAL_DIRECTORY 和本地 file URI；NETWORK_SHARE、OBJECT_STORAGE 与 READ_ONLY_ARCHIVE 保留在 Schema 中，但由本原型以配置不支持明确拒绝。

verify 只读取 Manifest 与九个从属输出，不读取原 SourceMount，也不依赖扫描机器的绝对根路径。全新目录复制完整输出后必须能够独立验证。

后续 compare、migrate-paths 和 summarize 不属于本原型实现范围。

## 5. 模块职责

### 5.1 config 与 contracts

config 负责：

- 使用冻结 IngestConfig fragment 校验配置；
- 解析 SourceMount 当前部署绑定；
- 计算有效配置 JCS SHA-256；
- 校验 read_only=true、契约版本、规则版本和输出位置；
- 拒绝未知字段、重复键和非标准 JSON 数值。

contracts 负责：

- 加载四个版本化 Schema；
- 建立跨 Schema Registry；
- 提供顶层和公开 fragment Validator；
- 校验 contract-lock.json；
- 禁止运行时替换未知主版本。
- 对 EngineeringResult 保留契约边界测试：IMPORTED 只能是 UNVERIFIED，且不得携带受信执行尝试或执行指纹。本原型不实现 Claim/Evidence 支撑判定，也不存在把 Imported 结果提升为成功证据的输出路径。

### 5.2 paths 与 discovery

paths 负责：

- 将路径转换为挂载根内相对路径；
- 分隔符统一为 /；
- Unicode NFC；
- 按 case_policy 产生 path_key；
- 拒绝盘符、UNC、URI scheme、前导斜杠、反斜杠、空段、点段、父级越界、控制字符、冒号和 NTFS ADS；
- 检测 NFC/casefold 碰撞；
- 判断输出及暂存目录是否位于挂载根内。

discovery 使用 os.scandir 做确定性遍历：

- 不跟随 symlink、Junction 和 reparse point；
- 按规范相对路径 UTF-8 字节序排序；
- 快速剪枝 .venv、venv、node_modules、__pycache__、.git、dist、build、target、coverage 和配置缓存目录；
- 只读取元数据，不修改源文件。

emit_excluded_item_records=false 时，快速剪枝目录只增加 pruned_directories，不声称知道内部文件数。emit_excluded_item_records=true 时，以元数据模式遍历被剪枝目录并逐项产生 EXCLUDED + SKIPPED_BY_POLICY 记录，但不打开文件内容；每条记录必须保存命中规则 ID。128 文件验收配置固定启用逐文件排除记录。

### 5.3 preflight 与 hashing

preflight 根据路径、文件名、扩展名、文件签名和安全浅层元数据生成规则命中。规则只产生建议和处置，不执行脚本、宏、二进制或外部链接。

hashing：

- 以只读二进制流分块计算 SHA-256；
- Hash 前后读取 size 与 mtime_ns；
- 任一变化产生 FILE_CHANGED_DURING_SCAN；
- Hash 失败或变化时不产生 content_hash 和 source_occurrence_key；
- 通过依赖注入的文件访问接口支持确定性故障测试，默认实现只使用本地只读文件 API。

### 5.4 classification、sensitivity 与 issues

classification 输出 20 项冻结 ArtifactRole 中的一个自动建议，且固定：

~~~text
classification_status = PROPOSED
classification_authority = AUTOMATED_SUGGESTION
~~~

ArtifactIngestRecord 禁止 MANUAL_OVERRIDE 和 VERIFIED_REFERENCE。

分类置信度低于 0.60，或同优先级规则产生冲突时，主处置固定为 NEEDS_REVIEW。仅靠扩展名的业务角色建议最高为 0.70；路径、文件名、签名和能力包规则一致时可以提高置信度，但每条 classification_reasons 必须能够复算。

sensitivity 使用路径、文件名、配置规则和安全文本信号标记：

- FACE_IMAGE；
- PERSONAL_DATA；
- QUESTIONNAIRE；
- INTERVIEW；
- DATABASE_DUMP；
- CREDENTIAL；
- SOURCE_CODE；
- VIDEO；
- AUDIO。

首轮不引入人脸识别模型。人脸、头像、问卷、访谈等只能根据可解释信号标记；证据不足时进入人工复核。凭证规则只记录规则 ID、位置类别、置信度和遮罩摘要，禁止保存命中的 secret。

issues 只使用冻结 error_code、stage 和 severity。消息、日志和摘要不得包含绝对个人路径、凭证或完整敏感正文。

### 5.5 deduplication、candidates 与 references

deduplication 只按同一扫描内的 SHA-256 精确分组：

- 规范候选必须为 pre_dedup_decision=ACCEPTED 且 pre_dedup_parser_eligible=true；
- 选中者保持 ACCEPTED + parser_eligible=true；
- 其他合格成员变为 DUPLICATE + parser_eligible=false；
- EXCLUDED、QUARANTINED 和 NEEDS_REVIEW 保持更严格处置；
- 无合格成员时为 NO_ELIGIBLE_CANONICAL；
- 规范代表只用于避免重复解析，不等于正文或工程主版本。

candidates 在单个 project_scope 内生成：

- PRIMARY_DOCUMENT；
- PRIMARY_ENGINEERING_ROOT。

正文候选排除备份、自动保存、模板、数据手册、旧论文、第三方依赖和构建产物。评分特征包含文件名、角色、修改时间低权重、可用页数或字数及版本关系。缺少安全元数据时不得伪造。

正文候选 v0.1 权重冻结为：

- PRIMARY_DOCUMENT 角色：0.30；EXISTING_DRAFT：0.20；
- 当前正文文件名信号：0.25；
- 安全支持的 DOCX：0.15，PDF：0.10；
- word_count 不少于 500：0.10；
- 同范围最新 mtime：0.05；
- 位于范围根或明确正文目录：0.10；
- 备份、模板、旧论文、数据手册、第三方依赖、构建产物：ELIGIBLE=false，不进入推荐。

PRIMARY_ENGINEERING_ROOT 使用“根锚点 Artifact”适配冻结 Schema。锚点优先级固定为 pyproject.toml、requirements.txt、manage.py、package.json、README.md；同一根存在多个锚点时选择优先级最高者，没有这些文件时该目录不形成工程根候选。candidate_ingest_record_ids 引用锚点记录；根相对路径、源码数量、锁文件、迁移、测试和启动说明信号写入 feature_values。recommended_ingest_record_id 只表示获推荐工程根的锚点，不等于把单个文件认定为完整工程，也不替代后续人工根选择。

工程根 v0.1 权重冻结为：有效锚点 0.20、至少 3 个源码文件 0.20、依赖或锁文件 0.15、测试目录 0.15、迁移脚本 0.10、README/启动说明 0.10、框架项目配置 0.10。

状态固定为：

- 最高分不低于 0.70，且无第二名或领先超过 0.05：RECOMMENDED；
- 最高分不低于 0.70，且与第二名差值不超过 0.05：TIED_REVIEW；
- 最高分低于 0.70、无合格项或证据不足：NO_RECOMMENDATION。

冻结 Schema 要求 candidate_ingest_record_ids 至少一项，因此 NO_RECOMMENDATION 表达“已经观察到一个或多个展示项，但没有可靠推荐”。备份等不合格项可以只作为版本关系展示并保留低分或 ELIGIBLE=false 特征，禁止成为 recommended 或 tied 项。范围内完全没有可观察文件时不伪造 PrimaryArtifactCandidate，而是记录 PROJECT_SCOPE_UNRESOLVED Issue。

references 从裸 TXT 行、旧论文参考列表和文件名线索生成 ReferenceCandidate，固定 verification_status=UNVERIFIED、relevance_status=UNKNOWN、license_status=UNKNOWN。CLI 不创建 EvidenceChunk、Claim、VerifiedReference 或正文引用证据。

### 5.6 checkpoint、output 与 verification

checkpoint 保存扫描 ID、契约版本、配置 Hash、SourceMount ID、binding_revision、路径版本、规则版本、已发布分段及其 Hash、计数、最后完成的确定性游标和恢复次数。

output 只写输出目录旁的隐藏暂存区：

~~~text
.<output-name>.staging/<scan-id>/
├── checkpoint.json
├── work/
└── publish/
~~~

正式 ingest-output 只有在所有输出完成并验证后才发布。scan 要求目标输出目录不存在或为空；非空正式输出不被静默覆盖。publish 子目录最终只包含十个标准输出，验证完成后在同一父目录内原子改名为正式输出。JSONL 使用 UTF-8、无 BOM、LF、末尾换行和 JCS 紧凑序列化；每行一个对象，不允许空行。

verification 校验：

- 四个 Schema 和公开 fragment；
- 五类互斥处置计数；
- Artifact 分区行数；
- 引用存在性和 scan 一致性；
- DuplicateGroup 成员与规范代表资格；
- Candidate 引用与状态条件；
- SensitiveItem 与主记录字段一致；
- RootFingerprint 计数、强度和重算值；
- 九个固定输出路径及唯一 Schema route；
- 每个文件的字节数、记录数和 SHA-256；
- JSONL 截断、重复键、非法数值和篡改。

## 6. 扫描数据流

~~~text
加载并校验配置与契约
→ 校验 SourceMount、输出路径和暂存区
→ 确定性目录发现与快速剪枝
→ 路径规范化、越界和碰撞检查
→ 安全预检
→ 流式 SHA-256 与前后状态复核
→ ArtifactRole 和敏感分类建议
→ 精确 Hash 去重
→ 正文/工程主版本候选
→ 参考文献候选
→ 分批写入暂存 JSONL
→ Schema 与跨文件语义验证
→ 计算九个从属输出 Hash
→ 写入并验证 COMPLETED Manifest
→ 原子发布正式输出
~~~

Artifact 记录不保存绝对路径。SourceMount 单独保存部署所需 root_uri，但 root_uri 不进入业务身份。

ingest_record_id 对 scan_id、source_mount_id 和 observed_relative_path 的冻结投影计算。

source_occurrence_key 仅在 Hash 成功且文件稳定时，对 source_mount_id、relative_path 和 content_hash 的冻结投影计算。更换 root_uri 不改变未改文件的来源发生键。

RootFingerprint 对全部已发布记录的冻结投影排序、JCS 和 SHA-256 计算；非 COMPLETED 状态不得携带根指纹。

## 7. 预检与主处置

每个文件只有一个最终 ingest_decision：

- ACCEPTED；
- EXCLUDED；
- QUARANTINED；
- DUPLICATE；
- NEEDS_REVIEW。

严格优先级为：

~~~text
凭证、可执行、转储、可疑二进制
> 明确噪声和第三方依赖
> 敏感限制
> 低置信人工复核
> 正常接受
~~~

首轮最小规则：

- .venv、venv、node_modules、site-packages、vendor、__pycache__、.git、dist、build、target、coverage：EXCLUDED；
- 缓存、自动保存、备份、第三方依赖、构建产物：EXCLUDED；
- exe、dll、bat、cmd、ps1、jar、数据库转储、凭证风险、未知二进制和可疑压缩包：QUARANTINED；
- py、js、ts、java、sql 等正常工程源码不因“可执行文本”概念被误隔离；
- 扩展名与签名冲突：QUARANTINED 或 NEEDS_REVIEW；
- 低置信或规则冲突：NEEDS_REVIEW；
- 重复关系不得把严格处置降低为 DUPLICATE。

逻辑隔离不删除、不移动、不复制、不执行、不解压源文件。

## 8. 恢复与原子发布

CHECKPOINT_STRICT 恢复要求契约版本、配置 Hash、SourceMount ID、binding_revision、路径版本和规则版本完全一致。

恢复时必须重新核对已处理源文件的 size、mtime_ns 和已知 Hash。源文件变化时产生 SOURCE_MUTATED_DURING_SCAN 并拒绝复用旧 Checkpoint。

分段 JSONL 和 Checkpoint 使用临时文件、flush、关键文件 fsync 与 os.replace。中断时：

- 暂存区保留 PARTIAL Manifest；
- 不发布 COMPLETED；
- 相同上下文可继续；
- 稳定记录 ID 和分段 Hash 防止丢行及重复。

RESTART_SCAN 创建新 scan_id，并将旧暂存区原子改名到 abandoned 子目录留作诊断，不修改源文件，也不静默复用旧记录。

Manifest 最后生成。九个从属输出、Schema、跨文件关系、Hash 和 Manifest 自身结构全部通过后，才把同卷 publish 目录原子改名为正式输出；禁止用逐文件覆盖冒充整包原子发布。

## 9. 错误与退出码

启动级错误立即停止且不创建正式输出：

- CLI 参数或配置无效；
- SourceMount 不存在或不可读；
- read_only 不为 true；
- 输出或暂存目录位于挂载根内；
- 路径、规则或契约版本不兼容；
- Checkpoint 上下文不匹配。

逐文件错误形成 IngestIssue 后继续：

- FILE_UNREADABLE；
- HASH_FAILED；
- FILE_CHANGED_DURING_SCAN；
- TYPE_SNIFF_FAILED；
- EXTENSION_SIGNATURE_MISMATCH；
- CLASSIFICATION_AMBIGUOUS；
- PATH_NORMALIZATION_COLLISION。

失败记录进入 QUARANTINED 或 NEEDS_REVIEW，不生成内容身份，不进入 Parser。

发布级错误阻止 COMPLETED：

- JSONL 截断或重复键；
- Manifest 计数不一致；
- 引用缺失；
- Schema route 错误；
- 输出 Hash 不匹配；
- 原子发布失败。

退出码冻结为：

~~~text
0  COMPLETED 且完整验证通过
2  CLI 参数或配置无效
3  SourceMount 或路径安全错误
4  扫描中断，保留 PARTIAL 和 Checkpoint
5  输出或 Verify 完整性失败
10 未预期内部错误
~~~

逐文件失败只要完成安全降级和审计，可以形成带 Issue 的 COMPLETED Manifest。

## 10. 固定夹具

tests/fixtures 通过声明文件和确定性生成器构建 128 个文件。全部夹具为合成材料或可再分发公开快照，不复制历史论文库、真实照片、真实问卷、真实数据库或真实凭证。

夹具包括：

- 最小合法 DOCX、PDF、PNG 和文本；
- 源码、配置、测试和数据库迁移；
- 学校模板和带来源/许可说明的公开资料快照；
- 多个正文终稿、旧论文、备份和自动保存版本；
- 精确重复和同名不同内容；
- 虚拟环境、第三方依赖、缓存和构建产物；
- 只有安全文件头、无可执行逻辑的 EXE/DLL 样本；
- 假数据库转储、假凭证和可疑压缩包；
- 裸参考文献 TXT；
- 合成人脸命名图片、问卷、访谈、视频和音频安全样本；
- Unicode、大小写碰撞和越界路径负向输入。

生成器固定随机种子、内容、目录、mtime 和期望分类清单。公开快照必须随附来源、许可和抓取日期；测试不在运行时联网。

## 11. TDD 与测试矩阵

所有生产函数先有失败测试，再写最小实现。每个 Red 阶段必须记录预期失败原因，Green 后运行相关测试和全量测试。

首轮目标不少于 80 条：

| 测试组 | 最低数量 |
| --- | ---: |
| 路径与身份 | 12 |
| 预检与主处置 | 14 |
| Hash 与去重 | 12 |
| ArtifactRole 与敏感标记 | 12 |
| 主版本与参考候选 | 10 |
| Manifest、JSONL 与 Verify | 12 |
| Checkpoint 与恢复 | 6 |
| CLI 端到端 | 5 |

契约测试还必须覆盖 Imported EngineeringResult：合法的 IMPORTED + UNVERIFIED 可归档；IMPORTED + VERIFIED、Imported 携带执行尝试或执行指纹均被拒绝。由于本阶段不实现 Claim 和 Evidence，测试同时断言 CLI 不生成任何成功 Claim 支撑记录。

恢复至少覆盖：

1. 发现阶段中断；
2. Hash 批次中断；
3. 分类阶段中断；
4. JSONL 分段写入中断；
5. Manifest 发布前中断；
6. Checkpoint 损坏、配置变化或源文件变化。

安全负向场景不少于 12 个：

- 绝对 relative_path；
- 父级越界；
- UNC；
- 输出根内；
- symlink 或 reparse point；
- Unicode/case 碰撞；
- EXE/DLL；
- 凭证风险；
- 数据库转储；
- 可疑压缩包；
- 扫描期间变化；
- Hash 失败；
- 篡改输出；
- 伪 COMPLETED。

测试使用真实临时文件和真实 JSON/JSONL。只有文件系统故障、时钟和中断点允许通过明确接口注入，不添加只供测试调用的生产命令。

## 12. 验收

最终必须执行：

~~~powershell
python -m pytest -q
python -m thesis_ingest scan --config ingest-config.json --output ingest-output/
python -m thesis_ingest verify --manifest ingest-output/ingest-manifest.json
~~~

验收必须证明：

- 128 文件夹具可从全新目录确定性生成并扫描；
- 四个冻结 Schema 和全部公开 fragment 校验通过；
- 九个输出完整且 Manifest 计数、引用、路由和 Hash 一致；
- 更换 SourceMount root_uri 后未修改文件的 source_occurrence_key 不变；
- 中断恢复无丢行、无重复；
- 源文件扫描前后逐文件 SHA-256 不变；
- 虚拟环境、缓存、依赖和构建产物不进入 Parser；
- 可执行、转储、凭证和可疑压缩包进入隔离；
- 数据手册、旧论文、第三方依赖和备份不成为当前正文推荐；
- 并列候选和无推荐均可合法输出；
- 裸参考文献只形成 UNVERIFIED Candidate；
- Imported EngineeringResult 保持 UNVERIFIED，不能经 CLI 形成成功 Claim 或 Evidence；
- 输出复制到全新目录后可独立 verify；
- 篡改任一从属输出后 verify 返回退出码 5；
- Python 单元、契约和端到端测试总数不少于 80，恢复场景不少于 6，安全负向场景不少于 12。

CLI 通过以上验收后，只冻结 Ingest CLI v0.1-Prototype。FastAPI、PostgreSQL、Redis、Worker 和平台主体开发仍需后续独立 P0-2 实施总包。

## 13. 变更控制

- feat/ingest-cli-v0.1 从 8d0e9fa 创建；
- 冻结 v0.1 Schema 只作为只读快照复制，不修改原文件；
- contract-lock.json 和契约测试阻止快照漂移；
- 新输出字段、枚举、身份投影、Hash 规则或状态语义必须发布 v0.1.1；
- 本原型不读取或扫描 15 万历史论文库；
- 本原型不修改 r2-r7 失败候选，也不启用自动 ProjectFact 治理。
