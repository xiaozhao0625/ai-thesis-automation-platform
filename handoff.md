# AI论文自动化生产平台｜2026-07-15 详细交接

## 1. 今日结论

今日工作已把项目从“UI/UX 基线已经通过、原型仍有工作流视觉与任务内导航缺口”的状态，推进到“v1.2.2 已完成可复现实现与浏览器级验收，可作为前端开发参考”的状态。

本次推送只包含可公开、可复现的前端原型和交接材料；不会上传用户原始论文资料、资料库、第三方 Skill、附件、个人路径或完整交接包。

## 2. 已确认的产品与研发基线

### 产品目标

- 面向平台运营者的自动化论文生产控制台，而非面向学生的聊天工具。
- V1.0 首先验证单个任务的全自动闭环，之后再扩展多任务、多账号并发。
- 第一能力包是 `python_web_management_v1`：Python Web 信息管理系统类工科毕业论文。
- 标准验收案例是“基于 FastAPI 与 PostgreSQL 的实验室设备管理系统设计与实现”。
- 首版固定参考技术栈：FastAPI、PostgreSQL、SQLAlchemy、Pydantic、Pytest、OpenAPI、Vue 3/管理端、Docker/本地进程。
- 重要主张必须可追溯至证据、引用或真实工程验证结果；不得伪造来源、数据、测试或引用。

### 研发基线

已完成 PRD v0.3、工作流节点契约、核心数据模型/ER、Worker 可靠性、标准基准样本/验收集、PaperDocument→DOCX 渲染规范，以及 v0.3.1 技术校正。关键约束包括：

- Outbox 与 QUEUED 语义分离；Worker 租约、心跳、幂等键、死信、恢复和 Outbox 可靠性均有明确边界。
- 首次执行加最多 2 次自动重试，合计最多 3 个 Attempt；人工重跑独立计数。
- 自动修订最多两轮；初检不计为修订轮次。
- 第六章测试内容必须等待真实工程验证；`quality_gate_final`、`export_render`、`delivery_approval` 独立。
- 目录或上游版本变更会使下游进入 `INVALIDATED`，旧输出只读保留，不能再作为有效输入。
- 三个人工闸门：启动确认、目录与技术路线确认、终稿交付审批。

## 3. UI/UX 基线演进

### 已保留的视觉规则

- 视觉主题：`Spectrum Ledger｜光谱账本`。
- 形态：高信息密度、低视觉噪声的论文生产控制台、证据审查台和工作流运行中心。
- 非 AI 聊天化：不使用聊天框主界面、营销式大卡片、粒子、网格、霓虹发光、大面积渐变或装饰性仪表盘。
- 左侧导航 232px、顶部栏 56px、右侧检查器 360px、表格行高 44px、1440px 主设计，1280px 兼容。
- 业务领域与运行状态是双通道：WorkflowNode 的 4px 顶边只表示领域；Badge/图标只表示生命周期。
- `engineering_verify` 任意状态下都保留工程绿 `#16825D` 顶边；RUNNING 使用克制的紫色 Badge；FAILED 使用红色左轨；BLOCKED 使用锁与琥珀 Badge；INVALIDATED 使用灰紫斜纹和状态文字。
- ApprovalBar 为内容之后的第三层操作区，高 64px、z-index 20，仅覆盖审批详情与风险区域；页面预留至少 88px 安全区。

### v1.2.1 已实现并保留的闭环

1. 目录变更影响确认后，章节/质量/交付相关产物失效。
2. DeadLetter 恢复创建新的 `source_parser_pdf_recovery_01`，保留旧 FAILED NodeRun、Attempt 3/3、错误和来源关联。
3. 质量复检创建 `ReviewRun #RR-008`，从 RUNNING 变为 SUCCEEDED，且不增加两轮修订上限。
4. 终稿审批自动选择 DeliveryPackage v3/审批闸门③，批准后返回交付页并启用正式下载与审计事件。

## 4. 本次 v1.2.2 实现

### 4.1 工作流画布重建

原有绝对定位节点和普通 `div` 旋转箭头没有继续修补，已替换为：

- 数据模型驱动的只读 DAG；节点拥有稳定的 `node_id`、中文显示名、技术 ID、阶段、运行状态、世界坐标和输入/输出端口。
- 独立世界坐标层：7 个阶段列，每列最小 232px；节点 180px 宽，左右 26px 安全边距。
- HTML WorkflowNode 层 + SVG `path` 边层；边通过端口 ID 绑定 `source:out → target:in`。
- 普通依赖为实线、阻断为点线、失效为虚线；除颜色外还有线型区分。
- 水平滚动、空白区拖动画布、60%—160% 缩放、适配画布；V1.0 没有拖拽改节点位置的编辑能力。
- 中文名称为主，如“工程自动验证”；`engineering_verify` 保留为次级技术信息。

### 4.2 INVALIDATED 原位表达

- 删除 v1.2.1 的底部重复失效节点面板。
- 目录影响后，章节生成、`quality_gate_final` 与 `DeliveryPackage v3` 在其原 DAG 位置变为 INVALIDATED。
- 领域顶边仍保留；新增灰紫斜纹、中文失效状态、原因文本及失效边。
- 章节折叠组显示“5 个节点已失效”；展开后显示 `section_generate_ch3` 到 `section_generate_ch7`，不会与折叠组重复。

### 4.3 统一任务导航与路由

- 已抽出同一 `TaskSubNavigation`，复用九个入口：总览、工作流、项目与材料、资料与证据、目录、内容、工程验证、质量、交付。
- 1280px 下导航横向滚动，质量与交付不会被隐藏。
- 面包屑“论文任务”和任务名称可点击，分别返回任务列表和任务总览。
- 任务内路由使用 `/tasks/task-001/{page}`；URL 中保留 `taskId` 与已有 `node`、`attempt`、`claim`、`source`、`version`、`issue`、`package` 等查询上下文。
- 通过 History API 支持后退、前进、刷新、复制深链接及节点检查器选择恢复。

## 5. 仓库结构与主要文件

```text
.
├─ nstl_index.html                         # 既有静态基线，未改动
├─ nstl_index_js.js                        # 既有静态基线，未改动
├─ nstl_paper_nav.js                       # 既有静态基线，未改动
├─ uiux-prototype/
│  ├─ prototype.html                       # v1.2.2 可点击原型
│  ├─ prototype.contract.test.mjs          # 静态契约测试
│  ├─ prototype.interaction.test.cjs       # Playwright/Chrome 浏览器交互测试
│  ├─ build_v122_doc.py                    # v1.2.2 DOCX 说明生成器
│  ├─ AI论文自动化生产平台_UIUX_v1.2.2_工作流布局与任务导航校正说明.docx
│  ├─ README.md
│  ├─ TEST_RESULTS.md
│  └─ screenshots/workflow-1440-initial.png
└─ handoff.md                              # 本文件
```

## 6. 验证结果

### 已通过

- `node prototype.contract.test.mjs`：通过。
- `node --test prototype.interaction.test.cjs`：7 个测试通过，0 失败。
- 交互覆盖：v1.2.1 四条状态闭环、原位 INVALIDATED、端口几何、阶段边界、章节折叠/展开、九项导航、后退/前进、刷新和深链接。
- 1440px 工作流初始状态已通过浏览器截图人工检查，截图位于 `uiux-prototype/screenshots/workflow-1440-initial.png`。

### 已知限制（请不要误判为已通过）

- 当前桌面环境的 Chrome 自动化在“整页截图”时可能卡住并触发工具重连，因此没有将长截图采集作为验收步骤。交互验收使用每次约 6 秒完成的短时浏览器测试。
- 当前环境未发现可用 LibreOffice/soffice，因此 v1.2.2 DOCX 已生成但没有完成 DOCX→PNG 像素级渲染验证。文档结构、内容和表格由生成脚本控制；后续在有 Word 或 LibreOffice 的环境中应补做视觉渲染检查。
- 当前原型是高保真可点击参考，不是生产前端工程；尚未接真实 API、权限、持久化、Worker、Outbox、工程沙箱和 DOCX 渲染服务。

## 7. 后续建议顺序

1. 将 `prototype.html` 拆分到真实前端工程的组件、路由、状态和测试目录；优先实现 TaskSubNavigation、WorkflowCanvas、WorkflowNode、ContextInspector、ApprovalBar。
2. 以 v0.3.1 的数据模型接入真实 `Task`、`WorkflowRun`、`NodeRun`、`NodeExecutionAttempt`、`ArtifactVersion`、`Claim`、`EvidenceChunk`、`ReviewIssue` 和 `DeliveryPackage`。
3. 并行建设四条技术原型：状态机/Outbox/INVALIDATED、工程沙箱与测试产物归档、Claim—Evidence—Citation 追溯、PaperDocument→DOCX→Validator。
4. 冻结标准验收样本：FastAPI + PostgreSQL 实验室设备管理系统、公开资料快照、固定源码/测试数据和 acceptance manifest。
5. 在可用 Office 渲染环境补做 v1.2.2 DOCX 视觉检查；在真实浏览器 CI 中保留并扩展本次 7 条测试。

## 8. Git 状态说明

本次工作在隔离分支 `agent/uiux-v122` 完成；主分支基线仅增加了 `.worktrees/` 忽略规则以确保本地隔离工作区不会误入库。推送时应将该分支明确合入/推送到远程默认仓库，提交范围限于本交接文件和 `uiux-prototype/`。

## 9. 项目目录整理（2026-07-15）

项目根目录已新增以下安全导航和归档入口：

- `00_项目导航/README.md`：所有一级目录的职责、保留规则和使用方式。
- `00_项目导航/项目目录规划与清理建议_20260715.md`：长期保留、可归档与可删除内容的判定依据。
- `06_当前交付与原型/v1.2.2_工作流布局与任务导航校正包/`：当前最新校正说明、可点击原型、两类测试、测试结果和 1440px 检查截图。
- `04_交接说明/README.md`：下一位项目经理/开发者的阅读入口。
- `90_可恢复归档/`：已创建，当前未移动或删除任何文件。

此次整理没有直接删除原有资料。`work` 中的旧版渲染输出、`__pycache__` 和完成合并后的 `.worktrees` 被列为后续候选项；在确认引用关系前，必须先进入 `90_可恢复归档`，不得直接物理删除。
