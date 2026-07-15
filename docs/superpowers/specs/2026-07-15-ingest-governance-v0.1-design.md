# 资料摄取、来源治理与工程结果统一模型 v0.1 设计规格

- 状态：`DESIGN_REVIEW`
- 日期：2026-07-15
- 适用范围：V1.0 资料治理研发基线与数据契约
- 后续参考实现：独立 Python CLI + JSON/JSONL 清单
- 本轮边界：只交付研发基线、4 个 JSON Schema 和 2 个示例 JSON，不实现 CLI、API、数据库、Worker 或页面

## 1. 背景与目标

现有平台已定义任务、工作流、证据链、工程验证、质量闸门和 DOCX 交付，但缺少文件进入 Parser、Evidence 和内容生产之前的统一治理层。真实论文库包含 15 万级文件、虚拟环境、依赖包、缓存、备份、构建产物、可执行文件、数据库转储和敏感资料，不能直接按目录或旧绝对路径接入。

本设计增加“资料摄取与来源治理层”，先冻结可离线验证的数据契约，后续再实现独立 Python CLI。目标是让每个文件在进入 Parser 前都经过可审计的路径归一化、预检、Hash、去重、角色分类、隔离判断和候选推荐，并保证结果可迁移到未来 FastAPI、PostgreSQL、异步 Worker 和对象存储实现。

本设计不改变以下已确认方向：

- V1.0 仍只启用 `python_web_management_v1`，保持固定资料包、单任务和固定模板。
- 不增加固定的第四个人工闸门；工程主版本、正文主版本和 ProjectFact 确认都属于启动闸门①的条件步骤。
- ProjectFact V1.0 继续采用 `MANUAL_CONFIRMED`；自动提取只能提供建议。
- 裸参考文献只能进入候选池，不能直接成为 `VerifiedReference` 或 `EvidenceChunk`。
- 本轮不导入完整 41.782 GiB 资料库，不建立向量库。

## 2. 方案选择

已比较并排除两种替代方案：

1. 直接建设 FastAPI + PostgreSQL。它会过早引入 ORM、迁移、鉴权、部署、异步调度和恢复语义，扩大本轮范围。
2. 只写概念说明、不冻结机器可验证契约。它无法作为后续 CLI、Worker 和数据库的共同验收基线。

采用的方案是：先交付研发基线和 JSON Schema；评审冻结后，再以独立 Python CLI + JSON/JSONL 清单实现离线参考模块。CLI 不是一次性脚本，其枚举、路径规则、Hash 规则、错误码和 Schema 将成为正式后端的兼容契约。

## 3. 本轮交付与文件布局

本轮正式基线包计划包含：

```text
v0.1_资料摄取来源治理与工程结果统一模型/
├── 资料摄取、来源治理与工程结果统一模型研发基线_v0.1.md
├── source-mount.schema.json
├── ingest-manifest.schema.json
├── artifact-ingest-record.schema.json
├── engineering-result.schema.json
├── ingest-config.example.json
└── ingest-manifest.example.json
```

后续 CLI 的标准输出目录冻结为：

```text
ingest-output/
├── ingest-manifest.json
├── source-mounts.json
├── artifacts.jsonl
├── excluded-items.jsonl
├── duplicate-groups.jsonl
├── primary-candidates.jsonl
├── reference-candidates.jsonl
├── sensitive-items.jsonl
├── ingest-issues.jsonl
└── summary.json
```

设计约束：

- `ingest-manifest.json` 和 `summary.json` 是单个 JSON 对象。
- 可能达到 15 万级的记录使用 UTF-8、每行一个完整对象的 JSONL；禁止把所有文件塞进单个巨大 JSON 数组。
- JSONL 每行必须可独立解析，行尾统一 `LF`，文件末尾保留换行；每行使用 JCS 紧凑序列化。
- JSONL 每行必须包含 `schema_version` 和用于判别 `$defs` 的 `record_type`，禁止空行。
- 所有正式 JSON/JSONL 禁止注释、`NaN`、`Infinity` 和重复键。
- 正式输出的记录顺序按各类对象冻结的稳定排序键排列；大规模实现可用已封口 chunk 和外部归并，不得依赖文件系统遍历顺序。`output_hashes` 对最终原始字节计算，验证时不重新格式化。
- 输出先写临时文件，完成校验和 Hash 后再原子替换正式文件；不允许把半成品标记为 `COMPLETED`。

## 4. 核心对象与职责

### 4.1 SourceMount

`SourceMount` 表示一个可迁移的来源挂载，不把物理绝对路径当成资料身份。

最小字段：

| 字段 | 语义 |
| --- | --- |
| `schema_version` | 固定为本契约版本。 |
| `source_mount_id` | 稳定、人工分配的挂载标识，例如 `thesis-library-2026`。 |
| `name` | 运营侧可读名称。 |
| `mount_type` | `LOCAL_DIRECTORY`、`NETWORK_SHARE`、`OBJECT_STORAGE`、`READ_ONLY_ARCHIVE`。V1.0 CLI 只执行 `LOCAL_DIRECTORY`。 |
| `root_uri` | 当前部署解析位置；可变化，不参与 Artifact 业务身份。 |
| `binding_revision` | `root_uri` 每次变更时递增；扫描记录保存所用 revision。 |
| `read_only` | 原始论文库必须为 `true`。 |
| `status` | `ACTIVE`、`OFFLINE`、`DISABLED`；只读属性由 `read_only` 独立表达。 |
| `case_policy` | `CASE_SENSITIVE` 或 `CASE_INSENSITIVE`，由 SourceMount 明确声明。 |
| `unicode_normalization` | V0.1 固定为 `NFC`。 |
| `path_normalization_version` | 路径规范版本，参与恢复兼容检查。 |
| `root_fingerprint` | 对摄取范围计算的版本化指纹对象；不包含盘符或绝对根路径。 |
| `last_scan_at` | 最近一次完整扫描完成时间。 |
| `access_policy` | 挂载默认访问策略，至少包含 `preview_policy`、`external_model_policy`、`export_policy` 和 `audit_required`；文件级更严格分类可以覆盖默认值。 |

`source_mount_id` 创建后不可修改。`root_uri` 可以从 `D:/2026毕设` 改成 `D:/work/2026毕设` 或其他服务器路径；变更只产生新的 `binding_revision`。只要文件相对路径与内容 Hash 不变，来源发生键就不变。

### 4.2 ArtifactIngestRecord

每个被逐文件枚举的普通文件必须产生且只产生一条规范摄取记录。该记录首先是“本次扫描观察与决定”的审计记录，不等同于未来正式 `ArtifactVersion`。低风险噪声可按明确规则跳过内容 Hash；无法读取、扫描期间变化或 Hash 失败的文件仍保留审计记录并关联 `IngestIssue`，但在修复并重扫前不得获得可移植内容身份，也不得进入 Parser、候选池或正式后端 ArtifactVersion。规范记录进入以下两个主分区之一：

- `artifacts.jsonl`：`ACCEPTED` 或 `NEEDS_REVIEW`。
- `excluded-items.jsonl`：`EXCLUDED`、`QUARANTINED` 或 `DUPLICATE`。

两类文件均使用 `artifact-ingest-record.schema.json` 验证，避免分区之间字段漂移。派生清单只引用 `ingest_record_id`，不复制完整原始记录。

身份分为四层，禁止混用：

- 扫描记录身份：`ingest_record_id`，回答“本次扫描观察到哪一个目录项”。它由 `scan_id + source_mount_id + observed_relative_path` 的 RFC 8785 JSON Canonicalization Scheme（JCS）投影计算 SHA-256，只在本次扫描内稳定。
- 来源定位身份：`source_mount_id + relative_path`，回答“规范化后文件从哪里来”。
- 内容身份：`content_hash`，回答“这些字节是什么”，也是跨路径去重依据。
- 可移植来源发生键：以下三元组，回答“某来源位置观察到哪个内容版本”。

```text
source_mount_id + relative_path + content_hash
```

持久化 `relative_path` 已是规范化路径。只有 `hash_status=COMPUTED` 且文件稳定时，才计算 `source_occurrence_key`；它使用上述三元组的 JCS 投影计算 SHA-256，更换物理根路径不会改变。文件重命名、移动或内容变化会生成新的 occurrence；仅内容相同但路径不同的文件通过 `duplicate_group_id` 建立关系，不被误当成同一来源位置。`SKIPPED_BY_POLICY` 或 `FAILED` 记录没有 `content_hash` 和 `source_occurrence_key`。未来正式 `Artifact` 的逻辑身份和 `ArtifactVersion` 版本身份由后端另行分配；不得把扫描记录 ID 或来源发生键直接当成业务主键。

核心字段分为六组：

1. 来源：`source_mount_id`、`binding_revision`、`observed_relative_path`、`relative_path`、`path_key`、`ingest_record_id`，以及满足条件时的 `source_occurrence_key`。
2. 文件事实：`hash_status`、`content_hash`、`size_bytes`、`modified_at`、`media_type`、`extension`。
3. 摄取决定：`ingest_decision`、`decision_reason_codes`、结构化 `decision_rule_matches`、`requires_review`、`parser_eligible`；规则命中至少记录 `rule_id`、信号类型和脱敏摘要。
4. Artifact 分类：`artifact_role`、`classification_status`、`classification_authority`、`classification_confidence`、`classification_method`、`classification_reasons`。
5. 数据分类：`data_classification`、`content_categories`、`access_recommendation`、`model_usage_restriction`。
6. 审计：`scan_id`、`rule_set_version`、`scanner_version`、`observed_at`、`issue_refs`。

### 4.3 摄取决定与 Artifact 角色分离

摄取决定回答“本轮能否进入后续流程”，Artifact 角色回答“这个文件是什么”。二者不得合并成一个枚举。

`ingest_decision`：

- `ACCEPTED`：可进入后续候选、Parser 或人工确认流程。
- `EXCLUDED`：明确噪声、第三方依赖、缓存或构建产物；不删除原文件。
- `QUARANTINED`：可执行、未知二进制、数据库转储、凭证配置或可疑压缩包；仅进入受控审阅。
- `DUPLICATE`：内容 Hash 与同一扫描中的规范代表相同；保留来源记录但不重复解析。
- `NEEDS_REVIEW`：分类置信度不足或规则冲突，不能自动进入 Parser。

`decision_reason_codes` 冻结为可扩展字符串代码。首批至少包含：

- `NOISE_DIRECTORY`
- `THIRD_PARTY_DEPENDENCY`
- `CACHE_FILE`
- `BUILD_OUTPUT`
- `BACKUP_OR_AUTOSAVE`
- `EXECUTABLE_CONTENT`
- `UNKNOWN_BINARY`
- `DATABASE_DUMP`
- `CREDENTIAL_RISK`
- `SUSPICIOUS_ARCHIVE`
- `CONTENT_HASH_DUPLICATE`
- `CLASSIFICATION_AMBIGUOUS`

`artifact_role` 首批枚举：

- `PRIMARY_REQUIREMENT`
- `PRIMARY_DOCUMENT`
- `ENGINEERING_SOURCE`
- `ENGINEERING_CONFIG`
- `ENGINEERING_RESULT`
- `SOURCE_IMAGE`
- `SOURCE_TABLE`
- `TEMPLATE`
- `REFERENCE_CANDIDATE`
- `VERIFIED_REFERENCE`
- `EXISTING_DRAFT`
- `GENERATED_DRAFT`
- `BACKUP`
- `THIRD_PARTY_DEPENDENCY`
- `BUILD_OUTPUT`
- `CACHE`
- `NOISE`
- `SENSITIVE_DATA`
- `EXECUTABLE`
- `UNKNOWN`

同一文件只有一个主 `artifact_role`，但可有多个 `content_categories`。业务角色、摄取决定和数据分类是三条正交轴：例如源码可以同时是 `ENGINEERING_SOURCE + ACCEPTED + INTERNAL`。`SENSITIVE_DATA` 只用于文件的主要性质就是敏感资料时；普通源码或数据库文件仍保留其业务角色，并通过数据分类轴表达限制。分类必须保存置信度、方法和理由；禁止只输出无依据的最终类型。

扫描器产生的分类一律为：

- `classification_status = PROPOSED`
- `classification_authority = AUTOMATED_SUGGESTION`

`PRIMARY_DOCUMENT` 和 `VERIFIED_REFERENCE` 等角色可以为未来正式模型保留，但扫描器不能据此赋予正式权威。`scan` 不得产出 `VERIFIED_REFERENCE`；正文候选即使被建议为 `PRIMARY_DOCUMENT`，也不等于已经完成主版本选择。只有后续人工选择、参考资料核验或可信系统导入，才能形成 `CONFIRMED + HUMAN_CONFIRMED/IMPORTED_VERIFIED` 的版本化 Assignment。CLI 输出包本身不能创建 `HUMAN_CONFIRMED`，`MANUAL_OVERRIDE` 分类方法也只为未来人工流程保留。

### 4.4 ArtifactRoleAssignment 与正式模型关系

CLI 记录中的分类是扫描时判断，不直接覆盖未来正式 Artifact。正式后端映射时：

- `ArtifactIngestRecord` 创建或关联 `ArtifactVersion`。
- 分类结果创建 `ArtifactRoleAssignment`，保存规则版本、置信度和审核状态。
- 人工修正追加新 Assignment，不覆盖历史判断。
- `ArtifactDependency` 继续表达原始材料、派生稿、工程结果和交付文件的直接血缘。

## 5. 路径、Hash 与去重规则

### 5.1 相对路径规范化

持久化 `relative_path` 必须满足：

- 相对 `root_uri` 计算，不允许盘符、UNC 根、URI scheme 或前导 `/`。
- 分隔符统一为 `/`。
- 去除 `.` 路径段；出现空段、`..`、NUL、控制字符、盘符、UNC 或 NTFS ADS 时直接产生阻断 Issue。
- Unicode 统一为 NFC；保留原始大小写用于展示。
- 按 SourceMount 的 `case_policy` 计算独立 `path_key`，禁止跨平台一律转小写。NFC/casefold 后碰撞时进入 `QUARANTINED` 并产生 `PATH_NORMALIZATION_COLLISION`，不得覆盖。
- 符号链接和 Junction 默认不跟随；未来允许跟随时，解析后的真实路径必须仍在 SourceMount 根内。
- 输出目录禁止放在 SourceMount 根内，避免扫描自身产物。

Artifact 记录和派生清单不得包含物理绝对路径。`root_uri` 只存在于 SourceMount/运行配置和受控诊断中。

### 5.2 内容 Hash

- 算法固定为 SHA-256，字符串格式为 `sha256:<64 lowercase hex>`。
- 对原始字节流计算，不做换行、编码、压缩解包或文本归一化；`hash_status` 为 `COMPUTED`、`SKIPPED_BY_POLICY` 或 `FAILED`。
- `SKIPPED_BY_POLICY` 只允许用于已经由路径/名称规则确定为 `EXCLUDED` 的低风险噪声；规则 ID 必须写入原因。`ACCEPTED`、`DUPLICATE`、主版本候选和参考文献候选必须具有 `COMPUTED` Hash。安全隔离文件原则上仍以只读字节流计算 Hash；若读取失败，保留 `QUARANTINED` 决定和 Issue，但不得形成内容身份。
- 文件必须流式读取，禁止把大文件一次性加载到内存。
- Hash 前后分别读取 size 与 mtime；扫描期间发生变化时记录 `FILE_CHANGED_DURING_SCAN`，本轮不接受该记录。
- `root_fingerprint` 是对象，至少包含 `algorithm`、`canonicalization_version`、`scope`、`strength` 和 `value`。它对本轮治理范围内全部已发布记录的 `(relative_path, size_bytes, hash_status, content_hash)` JCS 投影按规范相对路径 UTF-8 字节序排序后计算；未 Hash 项的 `content_hash` 投影为 JSON `null`。指纹明确排除 `root_uri`、摄取决定、mtime、inode、规则集、扫描时间和遍历顺序。默认 `scope=RECORDED_ITEMS`、`strength=MIXED`，表示“可治理扫描快照”；被目录级快速排除且未逐文件枚举的内容不进入该指纹，不得宣称是完整物理目录的强内容指纹。

### 5.3 去重

- 同一 `content_hash` 至少出现两次时生成 `DuplicateGroup`。
- 每个成员保留独立 `ingest_record_id` 和来源路径。
- `DuplicateGroup` 至少包含 `duplicate_group_id`、`content_hash`、`member_ingest_record_ids`、`canonical_ingest_record_id`、`canonical_selection_method` 和结构化选择理由。
- 技术上的 `canonical_ingest_record_id` 只用于避免重复解析，不代表论文正文或工程主版本。
- 规范代表按“非隔离记录优先、非备份优先、路径字典序”确定，规则版本化且可复算；规范代表必须存在于成员集合中。
- 精确重复只按 SHA-256 判断；文档近似度和版本相似关系只能写入候选比较信息，不得进入 `DuplicateGroup`。
- 业务主版本始终由 `PrimaryArtifactCandidate` 推荐并在启动闸门①人工确认。

## 6. 摄取预检与分类流程

冻结的数据流如下：

```text
读取并校验配置与 SourceMount
→ 挂载可用性、只读属性与输出路径检查
→ 枚举目录（快速排除目录级噪声）
→ 相对路径归一化、碰撞与越界检查
→ 路径噪声预检和安全文件类型嗅探
→ 按策略流式 SHA-256 与稳定性复核
→ 精确 Hash 去重分组
→ ArtifactRole 与敏感分类
→ 按最严格规则形成唯一摄取决定
→ 主版本候选、参考文献候选和敏感清单派生
→ JSON/JSONL 分批写出
→ Schema、计数和输出 Hash 校验
→ 原子发布 COMPLETED Manifest
```

### 6.1 快速排除目录

默认不进入内容遍历的目录名至少包含：

`.venv`、`venv`、`node_modules`、`__pycache__`、`.git`、`.idea`、`.vscode`、`dist`、`build`、`target`、`coverage`，以及能力包配置声明的缓存目录。

快速排除仍必须产生聚合审计计数；若配置要求逐文件清单，则以元数据模式枚举但不读取内容。不得删除、移动或修改被排除文件。

### 6.2 文件级排除与隔离

- 临时文件、自动保存文件、轮转日志、缓存和构建输出进入 `EXCLUDED`。
- 第三方依赖进入 `EXCLUDED`，不得成为工程源码主版本或 Evidence。
- `exe`、`dll`、`bat`、`cmd`、`ps1`、`jar`、未知二进制、数据库转储、凭证配置和可疑压缩包进入 `QUARANTINED`。
- 扩展名不能单独决定安全性；文件签名与扩展名不一致时以更严格决定为准并产生 Issue。
- 隔离只改变摄取决定，不对原文件执行删除、移动、复制、解压或运行。`QUARANTINED` 记录不得进入 Parser、模型输入、主版本候选或参考文献候选；只能进入受控审阅和完整性验证。

### 6.3 分类方法

`classification_method` 允许：

- `PATH_RULE`
- `FILE_NAME_RULE`
- `EXTENSION_RULE`
- `CONTENT_SIGNATURE`
- `METADATA_RULE`
- `CAPABILITY_PACK_RULE`
- `COMPOSITE_RULE`
- `MANUAL_OVERRIDE`

自动分类冲突时使用保守优先级：安全隔离 > 明确排除 > 敏感限制 > 业务角色推荐。置信度低于规则集阈值或出现同优先级冲突时必须 `NEEDS_REVIEW`。每条记录只能有一个主 `ingest_decision`；`parser_eligible=true` 只允许出现在 Hash 已计算、决定为 `ACCEPTED` 且无阻断 Issue 的记录上。重复组中只有规范代表可进入一次 Parser，所有 `DUPLICATE` 成员的 `parser_eligible` 必须为 `false`。

### 6.4 安全浅层元数据与 Parser 边界

摄取预检只允许对已通过安全处置的文件读取候选排序所必需的浅层元数据，例如文件签名、容器目录、文档页数、文本近似字数和图片尺寸；必须使用不执行宏、不加载外部链接、不反序列化对象的只读提取器，并记录提取器名称与版本。该步骤不等于领域 Parser：不得生成 EvidenceChunk、ProjectFact、可信 EngineeringResult 或正文语义结论。未知格式、加密文件、宏文档和可疑容器不能为了获取页数或字数而降低隔离等级；读取失败时值为 `null` 并关联原因，禁止用 `0` 伪装成功。

## 7. 主版本候选

系统只能推荐，不能自动确认正式正文或工程根。

`PrimaryArtifactCandidate` 最小字段：

- `candidate_id`
- `candidate_scope_id`：由配置中的项目根、人工指定范围或版本化目录识别规则产生；表示材料包或明确目录快照范围，禁止跨全库排名。
- `selection_type`：`PRIMARY_DOCUMENT` 或 `PRIMARY_ENGINEERING_ROOT`
- `candidate_ingest_record_ids`
- `recommended_ingest_record_id`
- 每个候选的文件名、`content_hash`、`modified_at` 和可用的页数/字数
- `recommendation_score`（0 到 1）
- `recommendation_reasons`
- `comparison_metrics`
- `scoring_rule_version`
- `requires_human_confirmation`（固定为 `true`）

文档比较指标可包含文件名信号、Hash、修改时间、页数、字数和版本相似关系；修改时间只能是低权重信号，页数/字数必须记录提取器与版本。工程候选可以是 Git commit、目录快照或文件集合，并包含源码文件数、锁定依赖、测试、迁移脚本和启动说明，不能强制表示为单个源码文件。推荐分数必须记录评分规则版本、特征值和稳定平分规则。缺少解析能力时指标可以缺省，但不能伪造。`BACKUP` 和自动保存记录只可作为版本关系展示，默认不参与推荐；即使某范围只发现备份，也必须 `NEEDS_REVIEW`，不得自动晋升。

人工选择结果未来映射为 `PrimaryArtifactSelection`，必须记录候选、选择人、时间和理由，并参与 `TaskSpecification`、`ProjectFactSnapshot` 与 `execution_fingerprint`。选择变化使相关解析、证据、目录和正文失效。

## 8. 参考文献候选准入

状态链固定为：

```text
UNVERIFIED
→ METADATA_VERIFIED
→ FULLTEXT_VERIFIED
→ ELIGIBLE_FOR_EVIDENCE
```

任何阶段均可进入 `REJECTED`，并保留原因。CLI 只能产生 `UNVERIFIED`；DOI 格式命中只是候选，不代表 DOI、全文或许可已核验。只有 `ELIGIBLE_FOR_EVIDENCE` 的来源才能切分为正式 `EvidenceChunk`。

`ReferenceCandidate` 最小字段：

- `reference_candidate_id`
- `raw_reference_text`
- `title_candidate`
- `author_candidates`
- `year_candidate`
- `doi_candidate`
- `isbn_candidate`
- `url_candidate`
- `source_ingest_record_id`
- `source_locator`
- `extraction_method`
- `verification_status`
- `duplicate_of`
- `relevance_status`
- `license_status`
- `issue_refs`

旧论文文末条目、TXT 引用列表、文件名和目录索引都只能创建候选。`source_locator` 必须能表达页、段、行或记录号，不能只有文件名。裸字符串不得创建 `EvidenceChunk`，不得支撑 Claim，也不得自动升级为 `VERIFIED_REFERENCE`。CLI 产生的 `relevance_status` 与 `license_status` 只能是 `UNKNOWN`，后续核验系统才可推进。

## 9. 敏感数据分类

`data_classification`：

- `PUBLIC`
- `INTERNAL`
- `SENSITIVE`
- `RESTRICTED`

`content_categories` 至少支持：

- `FACE_IMAGE`
- `PERSONAL_DATA`
- `QUESTIONNAIRE`
- `INTERVIEW`
- `DATABASE_DUMP`
- `CREDENTIAL`
- `SOURCE_CODE`
- `VIDEO`
- `AUDIO`

摄取记录同时输出：

- `access_recommendation`：`STANDARD`、`RESTRICT_PREVIEW`、`ROLE_RESTRICTED`、`SECURITY_REVIEW_REQUIRED`。
- `model_usage_restriction`：`ALLOW`、`ALLOW_REDACTED_ONLY`、`LOCAL_MODEL_ONLY`、`DENY_EXTERNAL_MODEL`。
- `sensitivity_confidence`、结构化 `sensitivity_reasons` 和 `requires_review`；凭证检测信号只能记录规则代码、位置类别和脱敏摘要，不能保存命中的秘密原文。

分类只表达治理决定，本轮不实现 DLP、脱敏、密钥管理或多租户隔离。日志、Issue 和 Manifest 不得复制凭证、完整个人信息或敏感正文。派生产物未来默认继承来源中的最高分类，降级必须有人工审计记录。`ingest-output/` 自身可能暴露文件名、目录结构和敏感分类，默认按 `INTERNAL` 受控保存；导出包应支持在不改变业务身份的前提下移除 `SourceMount.root_uri`。

## 10. EngineeringResult 统一模型

`EngineeringResult` 统一表示工程验证结果，避免每个能力包创建独立结果表。

最小字段：

- `schema_version`
- `engineering_result_id`
- `result_type`
- `task_id`
- `node_run_id`
- `environment_snapshot`
- `input_artifact_version_ids`
- `output_artifact_version_ids`
- `status`
- `metrics`
- `execution_fingerprint`
- `started_at`
- `finished_at`
- `producer`
- `result_hash`
- `provenance`
- `provenance_type`：`TRUSTED_EXECUTION` 或 `IMPORTED`。
- `verification_status`：`UNVERIFIED`、`VERIFIED` 或 `REJECTED`。
- `node_execution_attempt_id`（可信执行结果必填）。

`result_type` 预留：

- `BUILD`
- `STATIC_CHECK`
- `UNIT_TEST`
- `API_TEST`
- `DATABASE_TEST`
- `SIMULATION`
- `MODEL_TRAINING`
- `CALCULATION`
- `HARDWARE_MEASUREMENT`
- `MANUAL_OBSERVATION`

V1.0 只启用前五种。`status` 为 `PENDING`、`RUNNING`、`SUCCEEDED`、`PARTIAL`、`FAILED`、`TIMED_OUT` 或 `CANCELLED`。`environment_snapshot` 至少冻结操作系统、运行时、依赖锁摘要、工具链与必要硬件信息；`metrics` 是带名称、数值、单位和统计口径的结构化数组，禁止用无单位自由文本代替。`execution_fingerprint` 绑定 TaskSpecification、主版本选择、输入 ArtifactVersion、环境和执行器版本。`result_hash` 对排除自身字段后的 JCS 结果载荷计算，避免自引用。

摄取器发现日志、CSV 或截图时只能推荐 `ENGINEERING_RESULT` Artifact；不能凭文件名创建可信成功结果。导入历史结果必须是 `IMPORTED + UNVERIFIED`。`TRUSTED_EXECUTION` 必须引用有效的 `node_execution_attempt_id`，并由正式执行器产生；终态结果必须有 `finished_at`，运行中结果不得伪造结束时间。失败、不完整和未验证结果必须可归档，但不得支撑“测试成功”类 Claim；即使 `SUCCEEDED` 也必须经 Validator 且未失效后才能进入 Evidence gate。本轮只冻结该数据契约，不执行工程验证，也不采集结果。

## 11. CapabilityPack 扩展接口

能力包职责扩展为：论文结构、Fact Schema、Artifact 分类规则、领域 Parser、Evidence 准入规则、EngineeringResult 类型、Validator、DAG 模板、术语表和 DOCX 规则。

V1.0 只允许一个主能力包。数据模型预留 `TaskCapabilityBinding`：

- `primary_pack_version_id`
- `secondary_pack_version_ids`
- `priority`
- `namespace`

V1.0 中 `secondary_pack_version_ids` 必须为空。多能力包规则冲突、DAG 合并和 Validator 合并属于 V2 非目标。

## 12. Manifest、配置与未来 CLI 契约

### 12.1 IngestManifest

`ingest-manifest.json` 至少包含：

- `manifest_version`
- `scan_id`
- `status`：`CREATED`、`RUNNING`、`PARTIAL`、`COMPLETED`、`FAILED`、`CANCELLED`
- `source_mount_id`
- `root_fingerprint`
- `started_at`
- `finished_at`
- `rule_set_version`
- `scanner_version`
- `total_files`
- `accepted_files`
- `excluded_files`
- `quarantined_files`
- `duplicate_files`
- `needs_review_files`
- `failed_files`
- `pruned_directories`
- `issue_count`
- `output_hashes`

`total_files` 只统计被逐文件枚举并形成 ArtifactIngestRecord 的普通文件；目录、未遍历的剪枝目录内部条目和仅形成挂载级 Issue 的对象不计入。五个主处置计数互斥，并必须满足：

```text
total_files
= accepted_files
 + excluded_files
 + quarantined_files
 + duplicate_files
 + needs_review_files
```

`failed_files` 是 `needs_review_files` 或 `quarantined_files` 中发生读取、Hash、类型识别等逐文件失败的派生子集，不重复参与等式；敏感项、候选、重复组和 Issue 数同样是引用式投影统计。目录级剪枝只计 `pruned_directories`，不得声称知道其内部文件数。`summary.json` 必须按处置、角色、媒体类型、敏感级别和 Issue 严重度聚合，并与 Manifest 计数一致，同时给出扫描耗时、恢复信息、未读取和未 Hash 数。

`output_hashes` 覆盖除 `ingest-manifest.json` 自身之外的全部正式输出，避免自引用 Hash；每项记录相对文件名、SHA-256、字节数、记录数和 Schema fragment。交付包外层可另行记录 Manifest Hash。只有 `COMPLETED` 可导入正式后端；此时 `finished_at`、`root_fingerprint` 和全部非 Manifest 正式输出 Hash 必填，其他状态禁止伪装成完整结果。

### 12.2 配置

`ingest-config.example.json` 展示：

- 单个 SourceMount 当前部署配置；一次 `scan` 只绑定一个挂载，多挂载由多次扫描和上层批次协调。
- 路径、扩展名和文件大小规则。
- 快速排除目录。
- 隔离规则和敏感分类开关。
- Hash 算法（V1.0 固定 SHA-256）。
- JSONL 批量 flush 大小和 checkpoint 周期。
- CapabilityPack 分类规则版本。
- 是否生成逐文件排除记录。
- 项目候选范围 `project_scopes` 的来源与边界。
- 符号链接策略（默认 `DO_NOT_FOLLOW`）、一致性策略和恢复策略。

配置还必须包含 `config_version`；扫描开始前验证 `read_only=true`、`source_mount_id` 唯一、规则版本兼容，以及输出目录不位于挂载根内。示例配置不得包含真实个人路径、凭证或原始资料内容。

### 12.3 未来命令

本轮只冻结命令形态，不实现入口：

```powershell
python -m thesis_ingest scan --config ingest-config.json --output ingest-output/
python -m thesis_ingest verify --manifest ingest-output/ingest-manifest.json
python -m thesis_ingest compare --left old/ingest-manifest.json --right new/ingest-manifest.json
python -m thesis_ingest migrate-paths --config ingest-config.json --legacy-index old-index.csv --output migrated.jsonl
python -m thesis_ingest summarize --manifest ingest-output/ingest-manifest.json
```

## 13. 分批写出与恢复语义

后续 CLI 必须支持 15 万级文件，不依赖一次性内存数组：

- 目录枚举、Hash、分类和 JSONL 输出均采用流式/有界批次。
- 运行期使用已封口的临时 chunk；checkpoint 保存 scan ID、SourceMount/binding revision、配置 Hash、规则集/扫描器/路径规范版本、已封口 chunk、各输出已提交行数及遍历游标。
- checkpoint 放在输出目录的内部工作子目录，不属于正式交付清单；成功发布后保留最小恢复元数据或按配置清理。
- 恢复前必须验证 SourceMount、配置 Hash、规则集版本和已有 JSONL 尾部完整性；不一致时拒绝续跑并产生 `CHECKPOINT_INCOMPATIBLE`。
- 同一输出目录必须加独占写锁；崩溃后的半行回退到最后已封口 chunk，不能仅按“最后一个路径”猜测恢复点。
- 提交顺序固定为：写完并同步 chunk → 校验行数与 Hash → 原子更新 checkpoint。恢复时以 checkpoint 的已提交行数为上限，截断未提交尾部后再继续，确保不丢行、不重复。
- 记录键和分区写入必须幂等；重跑不得产生重复行。
- 普通文件系统只承诺 `BEST_EFFORT` 一致性。扫描期间源目录发生增删改时产生 `SOURCE_MUTATED_DURING_SCAN`，本轮结果只能 `PARTIAL` 或重新扫描，不得静默发布 `COMPLETED`。
- 单文件失败不必终止全扫描，但阻断 Issue、计数和最终状态必须准确。输出写入或 Manifest 完整性失败时不得发布 `COMPLETED`。

## 14. 错误模型

`IngestIssue` 至少包含：

- `issue_id`
- `scan_id`
- `ingest_record_id`（尚未形成记录时可省略）
- `relative_path`（允许安全显示时）
- `stage`
- `error_code`
- `severity`
- `recoverable`
- `message`
- `recommended_action`
- `created_at`

首批错误码：

- `CONFIG_INVALID`
- `RULE_SET_INCOMPATIBLE`
- `SOURCE_MOUNT_NOT_FOUND`
- `SOURCE_MOUNT_UNREADABLE`
- `SOURCE_MOUNT_NOT_READ_ONLY`
- `SOURCE_BINDING_MISMATCH`
- `PATH_OUTSIDE_MOUNT`
- `PATH_NORMALIZATION_FAILED`
- `PATH_NORMALIZATION_COLLISION`
- `PATH_LINK_SKIPPED`
- `FILE_UNREADABLE`
- `FILE_CHANGED_DURING_SCAN`
- `HASH_FAILED`
- `TYPE_SNIFF_FAILED`
- `UNSUPPORTED_FILE_TYPE`
- `EXTENSION_SIGNATURE_MISMATCH`
- `CLASSIFICATION_AMBIGUOUS`
- `SUSPICIOUS_BINARY`
- `CREDENTIAL_RISK_DETECTED`
- `ARCHIVE_UNREADABLE`
- `REFERENCE_PARSE_FAILED`
- `PROJECT_SCOPE_UNRESOLVED`
- `PRIMARY_CANDIDATE_TIE`
- `CHECKPOINT_CORRUPT`
- `CHECKPOINT_INCOMPATIBLE`
- `SOURCE_MUTATED_DURING_SCAN`
- `OUTPUT_LOCKED`
- `OUTPUT_DISK_FULL`
- `OUTPUT_WRITE_FAILED`
- `OUTPUT_HASH_MISMATCH`
- `OUTPUT_COUNT_MISMATCH`
- `SCHEMA_VALIDATION_FAILED`
- `RECORD_REFERENCE_MISSING`
- `LEGACY_PATH_UNMAPPED`
- `LEGACY_HASH_MISMATCH`

`stage` 为 `CONFIG`、`MOUNT`、`DISCOVERY`、`PATH`、`PRECHECK`、`HASH`、`CLASSIFICATION`、`CANDIDATE`、`OUTPUT`、`VERIFY` 或 `MIGRATION`；`severity` 为 `INFO`、`WARNING`、`ERROR` 或 `BLOCKING`。逐文件可恢复错误生成 Issue 后允许继续；配置、挂载根、越根安全、输出完整性和恢复上下文错误阻止发布 `COMPLETED`。错误消息不得包含凭证或完整敏感正文。

## 15. 旧绝对路径迁移

未来 `migrate-paths` 的冻结规则：

1. 将旧绝对路径与已配置 SourceMount 的历史根前缀进行最长匹配。
2. 截取并规范化 `relative_path`，拒绝越界路径。
3. 定位当前 `root_uri + relative_path`，计算 SHA-256。
4. 有旧 Hash 时必须匹配；无旧 Hash 时标记 `NEEDS_REVIEW`，不得声称身份已验证。
5. 输出新三元组身份、迁移状态和审计 Issue。

迁移不得只做字符串替换；Hash 不一致时必须保留旧记录并报告冲突。

现有 r2-r7 ProjectFact 候选中的 `source_locator.file_path` 属于旧绝对路径语义。本轮只冻结未来兼容目标：经人工审阅的迁移结果应改为 `source_mount_id + relative_path + ArtifactVersion` 引用；不得借本轮重新启用已判定 `DEFERRED` 的自动 ProjectFact 治理，也不得把旧定位直接视为已验证来源。

## 16. JSON Schema 约定

本轮 4 个 Schema 统一使用 JSON Schema Draft 2020-12：

- 显式声明 `$schema` 和稳定 `$id`。
- `$id` 使用对应文件名：`source-mount.schema.json`、`ingest-manifest.schema.json`、`artifact-ingest-record.schema.json`、`engineering-result.schema.json`。
- 契约版本统一为字符串 `0.1`；Manifest 使用 `manifest_version`，其他实体使用 `schema_version`。
- 顶层对象使用 `additionalProperties: false`。
- 所有结构化嵌套对象同样封闭；真正的动态字典使用 `propertyNames` 和带类型的 `additionalProperties`，不允许空 `{}`。
- 所有时间使用带时区的 RFC 3339 `date-time`。
- Hash 使用统一正则 `^sha256:[0-9a-f]{64}$`。
- ID 使用可读字符串并设置非空/长度约束；不强制 UUID，允许确定性 Hash ID。
- `source_mount_id` 使用 ASCII slug；路径、原因码和错误码正则必须完整锚定。
- 数组型分类、原因码和 ID 引用使用 `uniqueItems: true`；置信度限定为 0 到 1。
- 枚举在 Schema 内冻结；可扩展原因码使用受格式约束的字符串数组。
- 使用 `if/then` 冻结关键不变量：`COMPUTED` 必须有 `content_hash` 与 `source_occurrence_key`，其他 Hash 状态禁止二者；`parser_eligible=true` 只允许 `ACCEPTED + COMPUTED`；`DUPLICATE` 必须引用重复组；`COMPLETED` Manifest 必须具有结束时间、根指纹和完整输出清单；可信 EngineeringResult 必须引用执行尝试。
- Schema 负责结构和可表达的条件约束；路径越根、跨文件引用存在性、Manifest 计数等式、记录排序、输出 Hash 和 JCS 字节规范由正式验证器执行，不能伪装成仅靠单文件 Schema 已保证。
- `source-mount.schema.json` 定义挂载与访问策略。
- `ingest-manifest.schema.json` 定义扫描汇总、状态和输出 Hash。
- `artifact-ingest-record.schema.json` 定义来源、决定、角色、敏感分类和审计字段。
- `engineering-result.schema.json` 定义跨能力包工程结果。

为保持“本轮仅 4 个 Schema”与“全部 JSON/JSONL 可机器验证”同时成立：

- `artifact-ingest-record.schema.json` 顶层验证 ArtifactIngestRecord，并在 `$defs` 中冻结带 `record_type` 判别的 `DuplicateGroup`、`PrimaryArtifactCandidate`、`ReferenceCandidate`、`SensitiveItem` 和 `IngestIssue`；对应 JSONL 文件逐行使用这些 fragment 验证。未 Hash 的排除/失败记录仍是扫描审计记录，但 Schema 明确禁止其携带 `source_occurrence_key`，导入器也不得映射为 ArtifactVersion。
- `source-mount.schema.json` 顶层验证单个 SourceMount，并在 `$defs/SourceMountCollection` 中验证 `source-mounts.json` 容器。
- `ingest-manifest.schema.json` 顶层验证 Manifest，并在 `$defs/Summary` 与 `$defs/IngestConfig` 中验证 `summary.json` 和 `ingest-config.example.json`。
- `excluded-items.jsonl` 复用 ArtifactIngestRecord 顶层 Schema，通过 `ingest_decision` 区分。

示例必须通过官方 `jsonschema` Draft 2020-12 验证器和 `FormatChecker`，不得复制 r7 的简化校验器。`ingest-manifest.example.json` 使用 `PARTIAL` 状态，作为单文件 Schema 示例，不伪造不存在的从属文件 Hash；完整 `COMPLETED` 跨文件 Hash fixture 留到 CLI 技术原型轮次。正式验证同时检查 UTF-8 无 BOM、LF、末尾换行、重复键、`NaN` 和 `Infinity`。

### 16.1 完整性与信任边界

SHA-256 和 Manifest 只能证明内容完整性，不能证明扫描器身份、人工审批或资料真实性。未来后端必须把 CLI 输出包视为不可信导入：先验证 Schema、输出 Hash、扫描器/规则版本和来源权限，再创建待审记录。不得仅凭 Manifest 将分类升级为 `HUMAN_CONFIRMED`、将候选升级为 `VERIFIED_REFERENCE`，或把导入的 EngineeringResult 视为可信成功证据。

## 17. 向正式后端迁移

| CLI 对象 | 正式后端实体 |
| --- | --- |
| `SourceMount` | `source_mount` |
| `ArtifactIngestRecord` | 经 Hash 与审阅后映射 `artifact` / `artifact_version`；未 Hash 记录只保留摄取审计 |
| 摄取决定 | `ingest_decision` |
| `DuplicateGroup` | `artifact_duplicate_group` |
| `PrimaryArtifactCandidate` | `primary_artifact_candidate`；人工确认另建 `primary_artifact_selection` |
| `ReferenceCandidate` | `reference_candidate` |
| 敏感分类 | `data_classification` / role assignment |
| `EngineeringResult` | `engineering_result` |
| `IngestIssue` | `ingest_issue` / `review_issue` |

未来 Worker 执行与 CLI 相同的规范化、Hash、分类和输出语义，只把记录写入 PostgreSQL 与对象存储。API、数据库和 Worker 不得重新定义不兼容枚举。

## 18. 验收设计

本轮文档与 Schema 验收：

1. 4 个 Schema 均通过官方 Draft 2020-12 metaschema 检查。
2. `ingest-config.example.json` 不含真实路径、凭证或敏感内容。
3. `ingest-manifest.example.json` 通过 Manifest Schema。
4. 提供正向和负向 Schema 实例检查，至少覆盖非法绝对 `relative_path`、非法 Hash、未 Hash 记录伪造内容身份、未知枚举、`COMPLETED` 缺结束时间、可信 EngineeringResult 缺执行血缘，以及导入包伪造 `HUMAN_CONFIRMED`/`VERIFIED_REFERENCE`。
5. 文档中的枚举、字段名和示例与 Schema 完全一致。
6. 对 Manifest、Summary 和各 `$defs` 构造最小有效实例，逐个验证；不能只验证两个示例文件。
7. 跨文件验证规则形成明确测试清单，包括五类主处置计数等式、所有引用存在、重复组规范成员合法、JSONL 无断行/重复键、输出 Hash 与字节数一致。

后续 CLI 技术原型验收：

1. 更换 SourceMount `root_uri` 后，未改动文件的 `source_occurrence_key` 不变；新的 `scan_id` 会产生新的扫描级 `ingest_record_id`。
2. 虚拟环境、缓存和构建产物不进入 Parser 候选。
3. 数据手册、电路图和依赖包 PDF 不成为正文主版本候选。
4. 第三方依赖不成为工程源码主版本候选。
5. 相同 SHA-256 文件形成 DuplicateGroup，且保留全部来源路径。
6. 备份和自动保存文件不能覆盖正式候选。
7. 裸参考文献只进入 `REFERENCE_CANDIDATE`。
8. 可执行文件、数据库转储、凭证风险和可疑压缩包进入 `QUARANTINED`。
9. 敏感文件获得数据分类、访问建议和模型使用限制。
10. 每条记录可追溯到 SourceMount 与规范相对路径，不持久化物理绝对路径。
11. 旧根路径迁移通过相对路径与 Hash 复核；Hash 冲突不得静默接受。
12. 15 万级扫描可分批写出、异常中断后安全恢复，且无重复记录。
13. 绝对路径、`..` 越界、符号链接/Junction 越根、Unicode NFC 和大小写碰撞均被阻断且不覆盖记录。
14. 文件在 Hash 期间变化时不得产生 `source_occurrence_key`；配置或规则变化后不得复用旧 checkpoint。
15. 伪装扩展名的 PE/脚本、未知二进制和可疑压缩包不被执行、不被解压，并进入逻辑隔离。
16. 同一 Hash 在不同路径可保留不同业务角色建议；精确重复与近似版本关系不能混组。
17. `.sql` 工程脚本可被接受，数据库转储被隔离；无法区分时进入复核，最严格决定优先。
18. 凭证配置的 Issue、日志和 Manifest 不泄露秘密原文，输出包按受控内部资料处理。
19. 截断 JSONL、篡改输出、引用不存在或计数漂移时，验证失败且不得发布/导入 `COMPLETED`。
20. `PrimaryArtifactCandidate` 不产生正式选择，裸 DOI/引用文本不超过 `UNVERIFIED`，失败或导入未验证的 EngineeringResult 不支撑成功 Claim。
21. 同一文件同时表达角色、处置和数据分类，三条轴互不覆盖；敏感投影和候选投影不重复增加 `total_files`。
22. 全过程不修改源文件；扫描对象的二进制、脚本、宏和外部链接从不执行。

## 19. 明确非目标

本轮不包含：

- Python CLI 实现或可执行扫描。
- FastAPI、PostgreSQL、ORM、数据库迁移和对象存储。
- Redis、Worker、队列、租约、心跳和死信。
- UI 页面或新的固定人工闸门。
- 文件删除、移动、解压、执行或自动修复。
- 实时公开检索、向量库、BM25、Reranker 或自动 Evidence 准入。
- 参考文献来源、全文、许可与最终相关性核验，以及任何 `EvidenceChunk` 生成。
- 自动选择正文或工程主版本。
- `migrate-paths` 命令实现、工程测试执行或 EngineeringResult 采集；本轮只冻结契约。
- 完整 DLP、自动脱敏、多租户隔离或密钥管理。
- 多能力包组合与跨领域 DAG 合并。
- 通用自动 ProjectFact 提取 r8。
- 将 41.782 GiB 原始资料库复制进平台工作区或 Git。
- 对正式后端并发或生产吞吐作承诺；15 万级分批与恢复属于后续 CLI 原型验收目标。

## 20. 后续顺序

1. 评审并冻结本设计。
2. 生成正式研发基线、4 个 Schema 和 2 个示例，并执行 Schema/交叉一致性验证。
3. 基线冻结后，按 TDD 实现独立 Python CLI 参考原型。
4. CLI 通过真实小样本和 15 万级压力验收后，再映射到 FastAPI、PostgreSQL、异步 Worker 和对象存储。
