# stackpilot

An evolving workflow agent for R&D teams, built around incident collaboration, AI-assisted code review, approval-gated actions, and auditable team learning.

[中文](#中文) | [English](#english)

---

## 中文

### 项目简介

`stackpilot` 不是一个泛化聊天机器人，也不是一个默认会自动执行高风险动作的 agent。

它的目标很具体：把研发团队常见的两类高价值流程放进同一个受控框架里。

- `事故协作`：读取飞书线程，结合本地知识库和团队规范，生成带引用的分析、总结和复盘草稿
- `AI 代码审查`：接收 GitHub PR 或 patch/diff，生成结构化 findings，并在审批后回写 GitHub

在这两条工作流下面，项目共享同一套内核能力：

- 线程 / 用户 / 组织级记忆
- 本地知识检索与 canonical policy 引用
- 动作草稿与人工审批
- interaction record 与 audit log
- skill candidate 挖掘与 canonical convention 推广

### 当前已实现

- [x] Feishu callback 接入与显式命令触发
- [x] 群聊线程读取、归一化与同线程 follow-up 记忆
- [x] 本地知识库检索，支持 runbook / release note / policy 路由
- [x] 结构化事故分析、结论摘要、待办草稿
- [x] 复盘草稿生成与线程内回写
- [x] 审批式动作队列
- [x] GitHub PR / inline patch 的 AI code review
- [x] 审批后将 review draft 发布为 GitHub comment
- [x] 在飞书线程内记录 finding 采纳 / 忽略反馈
- [x] 从 GitHub 侧同步 review outcome
- [x] skill candidate 草稿挖掘、注册与 canonical convention 写入
- [x] 全链路 interaction record 与 audit log

### 当前边界

- 默认只处理 `飞书群聊线程`，私聊消息会被忽略
- 所有高风险动作都走 `proposal-first + approval-first`
- 仓库不会自动改业务代码、自动提交 PR、自动发布外部评论
- `外部任务同步` 的适配器接口已经预留，但当前默认构建没有绑定真实任务系统

### 适用场景

- 值班群 / 故障线程里的快速研判与跟进总结
- 基于本地 SOP、runbook、release note 的证据补充
- 让代码审查输出更结构化、更可追踪
- 把“被反复证明有用”的团队做法沉淀为可审计规范

### 工作流概览

1. 用户在飞书线程里显式触发命令
2. 系统加载线程消息、历史记忆和相关知识文档
3. LLM 生成结构化分析或 review draft
4. 系统先返回草稿，再根据需要生成待审批动作
5. 用户通过线程命令批准动作
6. 系统执行回写、记录结果、更新记忆和审计日志

### 可直接触发的命令

#### 事故协作

- `分析一下这次故障`
- `分析故障原因`
- `总结当前结论`
- `总结一下`
- `基于最新信息重试`

#### 代码审查

- `帮我CR这个PR` + GitHub PR 链接
- `帮我review这个PR` + GitHub PR 链接
- `审一下这个diff` + patch / diff 内容
- `采纳 F1`
- `忽略 F2`
- `同步review结果`

#### 审批与沉淀

- `批准动作 A1`
- `批准动作 R1`
- `沉淀规范 skill-xxx`

### API

- `GET /healthz`
- `POST /api/feishu/events`

### 快速开始

Windows PowerShell:

```powershell
.\scripts\bootstrap.ps1
```

这会：

- 自动创建 `.env`
- 安装 Python 3.11
- 用 `uv` 安装依赖

启动开发服务：

```powershell
.\scripts\dev.ps1
```

默认地址：

- App: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Health check: [http://127.0.0.1:8000/healthz](http://127.0.0.1:8000/healthz)

运行测试：

```powershell
.\scripts\test.ps1
```

### 关键配置

复制 `.env.example` 后，至少需要补这些变量：

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_VERIFICATION_TOKEN`
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`

可选但常用：

- `GITHUB_TOKEN`
- `KNOWLEDGE_DIR`
- `MEMORY_DIR`
- `ACTION_DIR`
- `RECORDS_DIR`
- `SKILLS_DIR`

### 仓库结构

```text
app/
  api/            # Feishu callback route
  clients/        # Feishu / GitHub / LLM / task adapter clients
  core/           # config and logging
  models/         # shared contracts
  prompts/        # LLM prompts
  services/
    incident/     # incident analysis, action loop, postmortem
    review/       # code review parsing, rendering, publish, outcome sync
    retrieval/    # planner, router, ranker
    growth/       # skill mining, registry, convention promotion
    kernel/       # memory, action queue, audit, canonical conventions
data/
  knowledge/      # local docs and canonical knowledge
  memory/         # thread / user / org memory
  actions/        # pending action queue
  records/        # interaction records and audit logs
  skills/         # mined skill candidates
tests/            # pytest suite
```

### 设计原则

- `Explicit trigger only`：只响应显式命令，不做静默自治
- `Evidence before action`：先引用证据，再给判断
- `Draft before publish`：先出草稿，再审批发布
- `Memory with scope`：记忆只在 tenant / user / thread 范围内生效
- `Audit before evolution`：任何沉淀、推广、执行都要可追踪

### 相关文档

- [Product PRD](./rd-incident-ai-assistant-prd.md)
- [Feature List](./feature-list.md)
- [Technical Spec](./tech-spec.md)
- [Schema](./schema.md)
- [Evolution Architecture](./evolving-agent-architecture.md)
- [Decision Log](./decision-log.md)
- [Progress Log](./progress.md)

### 当前定位

`stackpilot` 现在更接近一个 `受控工作流 agent`，而不是一个“什么都能做”的智能体平台。

重点不在于自动化更多动作，而在于让事故协作和代码审查这两条流程：

- 更结构化
- 更可引用
- 更可审批
- 更可记忆
- 更可审计

---

## English

### What is stackpilot?

`stackpilot` is an evolving workflow agent for R&D teams.

It is not a generic chatbot and it is not designed to execute high-risk actions by default. Instead, it packages two concrete workflows into one controlled system:

- `Incident collaboration`: read Feishu threads, retrieve evidence from local knowledge and team policies, then generate structured summaries and postmortem drafts
- `AI code review`: accept GitHub PRs or raw patch/diff input, generate structured findings, and publish review output only after approval

Both workflows share the same kernel:

- thread / user / org memory
- local retrieval plus canonical policy citations
- proposal-first action queue
- interaction records and audit logs
- skill candidate mining and canonical convention promotion

### What works today

- [x] Feishu callback ingestion and explicit command routing
- [x] Thread loading, normalization, and follow-up memory
- [x] Local knowledge retrieval with runbook / release / policy routing
- [x] Structured incident analysis with citations
- [x] Conclusion summaries and todo drafts
- [x] Postmortem draft generation and write-back
- [x] Approval-gated action queue
- [x] AI code review for GitHub PRs and inline patch input
- [x] Approval-backed GitHub review comment publishing
- [x] In-thread feedback recording for accepted / ignored findings
- [x] GitHub-side review outcome sync
- [x] Skill candidate mining and canonical convention write-back
- [x] Interaction logging and audit trails

### Current boundaries

- Only `Feishu group threads` are handled by default; direct messages are ignored
- High-risk actions always require explicit approval
- The system does not autonomously rewrite product code or auto-publish external actions
- The `external task sync` contract exists, but the default local build does not wire a real task system adapter

### Best-fit use cases

- incident threads that need faster triage and clearer follow-up summaries
- evidence-backed discussion using local SOPs, runbooks, and release notes
- AI-assisted code review with structured findings and explicit outcome tracking
- turning repeated successful team behavior into auditable conventions

### Workflow

1. A user triggers a command from a Feishu thread
2. The system loads thread context, scoped memory, and relevant knowledge
3. The LLM produces a structured incident summary or review draft
4. The system returns a draft first, then proposes approval-gated actions if needed
5. A user approves actions from the same thread
6. The system writes back results and persists memory, records, and audit trails

### Supported commands

#### Incident workflow

- `分析一下这次故障`
- `分析故障原因`
- `总结当前结论`
- `总结一下`
- `基于最新信息重试`

#### Code review workflow

- `帮我CR这个PR` + GitHub PR URL
- `帮我review这个PR` + GitHub PR URL
- `审一下这个diff` + patch / diff content
- `采纳 F1`
- `忽略 F2`
- `同步review结果`

#### Approval and convention promotion

- `批准动作 A1`
- `批准动作 R1`
- `沉淀规范 skill-xxx`

### API

- `GET /healthz`
- `POST /api/feishu/events`

### Quickstart

Windows PowerShell:

```powershell
.\scripts\bootstrap.ps1
```

Start the app:

```powershell
.\scripts\dev.ps1
```

Run tests:

```powershell
.\scripts\test.ps1
```

Default local endpoints:

- App: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Health check: [http://127.0.0.1:8000/healthz](http://127.0.0.1:8000/healthz)

### Required configuration

At minimum, configure:

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_VERIFICATION_TOKEN`
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`

Common optional settings:

- `GITHUB_TOKEN`
- `KNOWLEDGE_DIR`
- `MEMORY_DIR`
- `ACTION_DIR`
- `RECORDS_DIR`
- `SKILLS_DIR`

### Repository layout

```text
app/
  api/            # Feishu callback route
  clients/        # Feishu / GitHub / LLM / task adapter clients
  core/           # config and logging
  models/         # shared contracts
  prompts/        # LLM prompts
  services/
    incident/     # incident analysis, action loop, postmortem
    review/       # code review parsing, rendering, publish, outcome sync
    retrieval/    # planner, router, ranker
    growth/       # skill mining, registry, convention promotion
    kernel/       # memory, action queue, audit, canonical conventions
data/
  knowledge/      # local docs and canonical knowledge
  memory/         # thread / user / org memory
  actions/        # pending action queue
  records/        # interaction records and audit logs
  skills/         # mined skill candidates
tests/            # pytest suite
```

### Design rules

- `Explicit trigger only`
- `Evidence before action`
- `Draft before publish`
- `Memory with scope`
- `Audit before evolution`

### Docs

- [Product PRD](./rd-incident-ai-assistant-prd.md)
- [Feature List](./feature-list.md)
- [Technical Spec](./tech-spec.md)
- [Schema](./schema.md)
- [Evolution Architecture](./evolving-agent-architecture.md)
- [Decision Log](./decision-log.md)
- [Progress Log](./progress.md)

### Positioning

Today, `stackpilot` is best understood as a `controlled workflow agent`, not a general-purpose autonomous agent platform.

Its value is not “doing more things automatically”. Its value is making incident collaboration and code review:

- more structured
- more evidence-backed
- more approval-safe
- more memory-aware
- more auditable
