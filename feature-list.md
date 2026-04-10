# P0 Feature List

## 1. Purpose

This document turns the PRD into a concrete functional checklist for P0.

P0 only needs to prove one product loop:

`用户在飞书线程中手动触发 -> 系统整理当前讨论并引用依据 -> 系统回一条结构化摘要`

This is not a generic roadmap. It is the implementation-facing functional boundary for the first working version.

## 2. Scope

Detailed scope in this document:

- P0 detailed feature list
- P0 non-goals
- P1 and P2 only as lightweight placeholders

Out of scope for detailed implementation here:

- Jira sync
- automatic incident detection
- hybrid retrieval
- long-term task orchestration

## 3. P0 Functional Inventory

| ID | Feature | Priority | Required In P0 | Mock Allowed |
| --- | --- | --- | --- | --- |
| F-001 | Feishu manual trigger | P0 | Yes | No |
| F-002 | Callback validation and safe ignore | P0 | Yes | No |
| F-003 | Current thread loading | P0 | Yes | Yes |
| F-004 | Thread normalization | P0 | Yes | No |
| F-005 | Local knowledge loading | P0 | Yes | Yes |
| F-006 | Citation lookup | P0 | Yes | Yes |
| F-007 | Structured summary generation | P0 | Yes | Yes |
| F-008 | Insufficient-context degraded reply | P0 | Yes | Yes |
| F-009 | Feishu thread reply rendering | P0 | Yes | No |
| F-010 | Health check and runtime readiness | P0 | Yes | No |

## 4. P0 Detailed Feature Definitions

### F-001 Feishu Manual Trigger

Goal:

- Let a user explicitly request analysis inside a Feishu message or thread.

User-visible trigger examples:

- `@机器人 分析一下这次故障`
- `@机器人 帮我总结当前结论`
- `@机器人 基于最新信息重试`

Inputs:

- Feishu callback payload
- bot mention or supported command text

Outputs:

- One accepted analysis request
- Or safe ignore when the message is unsupported

Normal behavior:

- Accept only supported explicit commands
- Anchor analysis to the message or thread where the user triggered it

Abnormal behavior:

- Ignore unrelated chatter
- Ignore unsupported message content safely
- Do not invent a trigger from ordinary discussion

Done criteria:

- Supported commands can be recognized consistently
- Unsupported messages do not enter the analysis path

### F-002 Callback Validation And Safe Ignore

Goal:

- Handle Feishu callback traffic safely before business logic begins.

Inputs:

- URL verification payloads
- subscribed event payloads

Outputs:

- Verification response when required
- Accepted message event
- Safe no-op for irrelevant events

Normal behavior:

- Respond to platform verification correctly
- Acknowledge supported message callbacks

Abnormal behavior:

- Missing required event fields must not crash the service
- Unknown event types must be ignored with logs

Done criteria:

- Callback route supports verification and message event handling
- Invalid events are contained and do not break the process

### F-003 Current Thread Loading

Goal:

- Read the current Feishu discussion context that the user wants analyzed.

Inputs:

- trigger message id
- thread id or equivalent discussion anchor

Outputs:

- ordered raw thread messages

Normal behavior:

- Load the message that was triggered and the visible thread context around it

Abnormal behavior:

- Empty thread should still produce a usable fallback analysis request
- Partial thread load failure should result in a degraded but safe response

Done criteria:

- One trigger can consistently resolve to one current discussion context

### F-004 Thread Normalization

Goal:

- Convert raw Feishu message data into one stable internal analysis contract.

Inputs:

- raw thread messages

Outputs:

- normalized `AnalysisRequest` object defined by `schema.md`

Normal behavior:

- Preserve message order
- Preserve sender and time information
- Keep only text useful for analysis

Abnormal behavior:

- Missing sender names or malformed timestamps must degrade safely
- Empty text content must be filtered or normalized, not passed through blindly

Done criteria:

- All downstream modules can rely on one normalized request shape

### F-005 Local Knowledge Loading

Goal:

- Make a controlled knowledge source available for P0.

Inputs:

- `KNOWLEDGE_DIR`
- local Markdown or text files

Outputs:

- available knowledge items for retrieval

Normal behavior:

- Read local docs at startup or on demand
- Expose enough metadata to cite the source later

Abnormal behavior:

- Missing knowledge directory must not crash the service
- Unreadable files should be skipped with logs

Done criteria:

- The service can see at least one local knowledge source when configured

### F-006 Citation Lookup

Goal:

- Provide source-backed evidence to support the summary.

Inputs:

- normalized thread context
- local knowledge items

Outputs:

- zero or more citation candidates

Normal behavior:

- Return a bounded list of the most relevant evidence snippets

Abnormal behavior:

- No knowledge hit must be allowed
- No result must not be turned into fake evidence

Done criteria:

- Citation objects follow `schema.md`
- The analysis layer can attach them to the final reply

### F-007 Structured Summary Generation

Goal:

- Produce one structured summary that a user can act on quickly.

Inputs:

- normalized thread context
- citation candidates

Outputs:

- `StructuredSummary` defined by `schema.md`

Required summary fields:

- `current_assessment`
- `known_facts`
- `impact_scope`
- `next_actions`
- `citations`
- `missing_information`

Normal behavior:

- Generate a concise and readable summary
- Use citations when evidence exists

Abnormal behavior:

- Weak evidence must lower certainty, not inflate confidence
- Missing information must be explicit

Done criteria:

- Output shape is stable
- User-visible sections match the PRD

### F-008 Insufficient-Context Degraded Reply

Goal:

- Respond safely when the system cannot support a strong conclusion.

Inputs:

- incomplete thread context
- weak or empty citations
- temporary analysis errors

Outputs:

- `insufficient_context` summary
- or `temporary_failure` reply

Normal behavior:

- Explain what is known
- Explain what is missing
- Suggest retry or additional input

Abnormal behavior:

- Never fabricate a precise cause from weak evidence

Done criteria:

- P0 has a safe fallback for low-evidence and temporary-failure cases

### F-009 Feishu Thread Reply Rendering

Goal:

- Return the result in a format users can immediately consume in Feishu.

Inputs:

- `StructuredSummary` or `TemporaryFailureReply`

Outputs:

- one formatted Feishu reply body

Normal behavior:

- Keep sections visually clear
- Reply in the same discussion context as the trigger

Abnormal behavior:

- If summary rendering fails, the service should still send a minimal failure notice when possible

Done criteria:

- Users can read the result without opening another tool

### F-010 Health Check And Runtime Readiness

Goal:

- Provide a minimal runtime signal for local development and deployment.

Inputs:

- none

Outputs:

- `/healthz` response

Done criteria:

- Service can expose a simple liveness endpoint

## 5. P0 Non-Goals

These features are explicitly excluded from P0:

- automatic incident detection
- same-thread memory as a hard requirement
- Jira or external task sync
- task state machine
- hybrid retrieval
- reranking
- postmortem draft generation

## 6. P1 Placeholder Features

These are not detailed for implementation yet, but reserved in product scope:

- F-P1-001 same-thread follow-up analysis
- F-P1-002 conclusion summary
- F-P1-003 todo draft generation

## 7. P2 Placeholder Features

- F-P2-001 external task sync
- F-P2-002 richer knowledge sources
- F-P2-003 postmortem draft generation

## 8. Acceptance Mapping

Each P0 feature should map back to these product promises:

- Manual trigger in Feishu
- Thread-scoped analysis
- Source-backed summary
- Safe degraded behavior
- Result returned in the same thread

If a code change does not help one of the above, it likely does not belong in P0.
