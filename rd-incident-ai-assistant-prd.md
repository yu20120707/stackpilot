# 研发工作流 Agent PRD

## 1. 文档信息

- 项目名称：研发工作流 Agent
- 项目定位：面向研发团队的受控成长型工作流 Agent
- 文档版本：v0.4
- 更新时间：2026-04-22
- 当前实现基础：飞书故障线程分析助手

## 2. 一句话定位

`一个以飞书、外部告警 webhook 和代码变更为主要入口，能够做故障协作分析、代码评审辅助，并在审批边界内持续沉淀团队经验的工作流 Agent。`

## 3. 背景与问题

研发团队里有两类高频但重复的协作工作：

1. `故障协作`
   讨论发生在飞书线程里，结论、依据、待办和复盘经常分散。
2. `代码评审`
   评审结论常依赖个人经验，标准不稳定，历史有效反馈难以沉淀。

如果只做一次性总结器，价值有限。
真正更值得做的是一个`受控成长层`：

- 会记录真实协作证据
- 会记住团队偏好
- 会提炼候选技能
- 会在审批边界内复用经验

## 4. 产品目标

1. 在故障协作场景下，稳定输出带依据的结构化判断。
2. 在故障场景下，把结论进一步推进到待办草稿和复盘草稿。
3. 在代码评审场景下，稳定输出结构化、证据化的 review findings。
4. 用统一的 memory、approval、audit、skill 机制承接两个场景。
5. 让系统“会成长”，但成长必须可审计、可回滚、可审批。

## 5. 产品边界

本产品要做：

- 飞书线程中的 incident workflow
- 外部告警 webhook 进入后归一化为 incident seed，并复用既有 incident analysis 链路
- diff / patch / PR 输入下的 AI code review workflow
- 审批约束下的任务草稿、复盘草稿、review 草稿
- 团队偏好记忆与候选 skill 沉淀

本产品不做：

- 通用聊天机器人
- 为了炫技而做多 agent 平台
- 自动改业务代码并直接提交
- 无审批自动发布评论或自动执行高风险外部动作
- 自动改写高权威项目文档
- 默认自动 incident detection
- 默认把外部告警自动变成新 Feishu 线程

## 6. 核心设计原则

### 6.1 Proposal First

高风险动作先出 proposal，再审批，再执行。

### 6.2 Evidence First

输出优先引用证据，不因为模型能说就给强结论。

### 6.3 Candidate First

可复用经验先变 skill candidate，不直接变 active rule。

### 6.4 Audit First

任何成长、审批、发布、执行都必须留痕。

## 7. 核心场景

### 7.1 Incident Analysis

用户在飞书线程中手动触发，系统读取线程、检索依据、输出结构化分析。

外部告警 webhook 也可以作为受控输入进入同一条 incident 分析链路，但它只会归一化成 incident seed，默认不会自动创建新的 Feishu 线程。
对告警输入，系统默认采用 triage-first 口径，先输出影响范围、缺失证据和首要动作，不直接承诺根因。

### 7.2 Incident Follow-up And Closure

系统基于 thread memory 和新增信息更新判断，并给出结论摘要、待办草稿、复盘草稿。

### 7.3 Controlled Incident Actions

系统先生成 task proposal / postmortem proposal，用户确认后再同步或回写。

### 7.4 AI Code Review

用户手动提交 diff、patch、commit range 或 PR，系统生成结构化 findings 和 evidence-backed review draft。

### 7.5 Controlled Growth

系统记录修正、采纳和失败结果，从中提炼候选 skill，但不会跳过审批直接生效。

### 7.6 Alert Ingress

外部监控或告警系统可以把规范化后的告警 payload 推给系统；系统先做归一化和证据整理，再根据是否已有 Feishu 锚点决定是回写到现有线程，还是只做后端分析与记录。
告警入口的输出默认是分诊结果而不是根因结论；如果证据不足，系统应明确列出缺失信息和下一步补证据动作。

## 8. 用户流程

### 8.1 Incident Workflow

1. 用户在飞书线程手动触发分析。
2. 系统读取线程与知识依据。
3. 系统输出结构化结论。
4. 系统可进一步输出 task draft 和 postmortem draft。
5. 用户确认后，系统执行外部同步或线程回写。
6. 系统记录采纳与修正结果，用于后续成长。

### 8.2 Code Review Workflow

1. 用户在飞书线程里手动提交 diff / patch / PR 链接并触发 review。
2. 系统先做输入解析，只保留一个可审查目标，然后把 PR 链接或 patch 标准化成 review request。
3. 如果是 PR 输入，系统拉取 GitHub diff，并用 DiffReader 把变更拆成文件、hunk 和摘要。
4. 系统补充 review focus、review policy citation 和团队规则依据，再拼成结构化输入交给 LLM。
5. LLM 返回结构化 review draft，系统保留 findings、风险等级、缺失上下文和发布建议。
6. 如果是 GitHub PR，系统先生成待审批的 publish action，用户确认后才真正发布到外部 review 平台。
7. 系统记录哪些 finding 被采纳、忽略或修正，并把 outcome 回流到 review state 和 memory。

## 9. 当前实现与后续扩展

### 9.1 当前实现基础

当前代码库已经具备：

- Feishu 手动触发
- 告警 webhook 接入与 Incident Seed 归一化
- 当前线程分析
- 本地知识引用
- 结构化 incident summary
- follow-up 输出
- todo draft
- postmortem draft
- confirmation-gated task sync contract

### 9.2 下一阶段重点

下一阶段不再重复堆“总结能力”，而是优先补这三层：

1. `显式状态`
   thread memory、user memory、org memory
2. `可审计闭环`
   action proposal、approval、execution、audit
3. `受控成长`
   recorder、feedback、skill candidate、approved reuse

## 10. 风险与取舍

主要风险：

- 过早把项目包装成通用 agent 平台，导致边界失控
- 把“自我进化”做成自动改主逻辑，后续无法审计
- 让弱证据驱动强结论
- 没有 proposal queue 和 approval policy 就开始做外部执行
- AI code review 一开始就覆盖过宽，失去可解释性

取舍原则：

- 先手动触发，再自动化
- 先结构化草稿，再外部发布
- 先 candidate，再 active
- 先 incident 闭环稳定，再复用到 AI CR

## 11. 成功指标

### 11.1 Incident 指标

- 手动触发成功率
- 引用依据的稳定性
- follow-up 连续性
- 草稿采纳率
- 审批后执行成功率

### 11.2 Code Review 指标

- 结构化 finding 可读性
- finding 采纳率
- 明显误报率
- 用户对 review 风格一致性的主观评价

### 11.3 Growth 指标

- 可复用候选 skill 数量
- 候选 skill 审批通过率
- active skill 复用率
- 发生回滚的比例

## 12. 版本规划

### P0 已完成基础

- 飞书 incident 分析最小闭环

### P1 显式状态层

- thread memory
- user/org memory 壳子
- 更稳定的 follow-up 连续性

### P2 Incident 闭环增强

- 轻量 Agentic RAG
- action proposal queue
- approval-backed task/postmortem execution

### P3 受控成长层

- interaction recorder
- audit log
- skill candidate registry
- approved reuse lifecycle

### P4 AI Code Review MVP

- 手动 review 触发
- diff 标准化
- 结构化 findings
- evidence-backed review draft
- draft-first publish flow

## 13. 一句话总结

这个项目最值得讲的版本不是“一个飞书总结机器人”，而是：

`一个面向研发团队的工作流 Agent：能在 incident 和 code review 场景下给出结构化、证据化输出，并通过记忆、反馈、审批和 skill 机制在边界内持续成长。`
