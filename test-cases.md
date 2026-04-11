# P0 Test Cases

## 1. Purpose

This document defines the minimum test coverage expected for P0.

The goal is not exhaustive QA. The goal is to ensure Codex and future sessions have clear acceptance targets for:

- happy path behavior
- unsupported input behavior
- insufficient-context safety
- failure-path user experience

## 2. Test Strategy

P0 testing should combine:

- unit tests for parsing and contracts
- fixture-based service tests for thread analysis
- manual verification for Feishu reply readability

Recommended fixture types:

- sample Feishu callback payloads
- sample thread transcripts
- sample knowledge documents
- expected structured summary outputs

## 3. P0 Acceptance Test Matrix

| ID | Category | Type | Must Pass For P0 |
| --- | --- | --- | --- |
| T-001 | Health | Automated | Yes |
| T-002 | Trigger parsing | Automated | Yes |
| T-003 | Unsupported message ignore | Automated | Yes |
| T-004 | Callback verification | Automated | Yes |
| T-005 | Thread normalization | Automated | Yes |
| T-006 | Knowledge citation hit | Automated | Yes |
| T-007 | Structured summary happy path | Automated | Yes |
| T-008 | Insufficient-context reply | Automated | Yes |
| T-009 | Temporary failure reply | Automated | Yes |
| T-010 | Feishu reply formatting | Manual + snapshot | Yes |
| T-011 | End-to-end fixture flow | Automated | Yes |
| T-012 | Unsupported chatter no-op | Automated | Yes |
| T-013 | Explicit thread memory continuity | Automated | Post-P0 |
| T-014 | Release evidence route preference | Automated | Post-P0 |
| T-015 | Weak evidence filtering | Automated | Post-P0 |
| T-016 | Pending action persistence | Automated | Post-P0 |
| T-017 | Approval-backed incident action execution | Automated | Post-P0 |

## 4. Detailed Test Cases

### T-001 Health Route Responds

Goal:

- Confirm the service is alive.

Preconditions:

- Application process is running.

Input:

- `GET /healthz`

Expected result:

- HTTP 200
- Response body contains `{"status":"ok"}` or equivalent

### T-002 Supported Manual Trigger Is Parsed

Goal:

- Confirm a valid Feishu command enters the analysis path.

Preconditions:

- Supported callback fixture exists.

Input:

- A message containing `@机器人 分析一下这次故障`

Expected result:

- Command parser returns `analyze_incident`
- Request is normalized into `AnalysisRequest`

### T-003 Unsupported Message Is Ignored

Goal:

- Confirm ordinary group chatter does not trigger analysis.

Input:

- A callback message such as `今天谁吃饭`

Expected result:

- No analysis request is created
- The service returns a safe acknowledge or ignore behavior

### T-004 Callback Verification Works

Goal:

- Confirm Feishu platform verification is handled correctly.

Input:

- URL verification payload fixture

Expected result:

- Verification response shape matches expected platform behavior
- No analysis logic is invoked

### T-005 Thread Normalization Produces Stable Shape

Goal:

- Confirm raw thread data becomes one stable internal contract.

Input:

- Feishu thread fixture with multiple messages

Expected result:

- Output matches `AnalysisRequest` schema
- Message order is preserved
- Empty message bodies are handled safely

### T-006 Citation Lookup Finds Relevant Evidence

Goal:

- Confirm local knowledge can produce citations for a relevant discussion.

Preconditions:

- Knowledge fixture directory contains at least one relevant document

Input:

- Normalized thread discussing a payment 5xx issue

Expected result:

- Retrieval returns one or more `KnowledgeCitation` objects
- Citations contain label, source path, and snippet

### T-007 Structured Summary Happy Path

Goal:

- Confirm the service can produce a full structured summary.

Preconditions:

- Thread fixture has enough discussion context
- Knowledge fixture contains relevant evidence

Expected result:

- Output matches `StructuredSummary`
- `status = success`
- Citations are present
- No required field is omitted

### T-008 Insufficient-Context Reply

Goal:

- Confirm weak evidence produces a safe degraded summary.

Preconditions:

- Thread fixture contains ambiguous discussion
- Knowledge lookup returns no reliable support

Expected result:

- `status = insufficient_context`
- `confidence = low`
- `missing_information` is not empty
- No strong conclusion is fabricated

### T-009 Temporary Failure Reply

Goal:

- Confirm temporary model or service failure produces a user-safe reply.

Preconditions:

- LLM client is forced to fail or timeout

Expected result:

- Output matches `TemporaryFailureReply`
- Includes retry hint
- Does not expose raw exception text

### T-010 Feishu Reply Formatting Is Readable

Goal:

- Confirm users can consume the reply in Feishu without confusion.

Type:

- Manual verification or snapshot-style rendering check

Expected result:

- Sections appear in the expected order
- Missing information is visible
- Citations are visible
- The reply is readable as a thread response

### T-011 End-To-End Fixture Flow

Goal:

- Confirm the full P0 flow works across modules.

Input:

- Supported callback fixture
- Thread fixture
- Knowledge fixture

Expected result:

- Callback is accepted
- Thread is loaded
- Citations are found or safely absent
- Structured reply is generated
- Reply payload is ready for Feishu send

### T-012 Unsupported Chatter Produces No Analysis

Goal:

- Ensure the bot is quiet unless explicitly triggered.

Input:

- Normal group discussion with no mention or command

Expected result:

- No analysis request is created
- No reply is generated

### T-013 Explicit Thread Memory Continuity

Goal:

- Confirm follow-up continuity can come from explicit persisted thread state instead of reply-text heuristics alone.

Input:

- Existing thread memory state
- Follow-up trigger in the same thread

Expected result:

- The service restores the previous summary from thread memory
- Only messages after the previous processed cursor are treated as new
- When memory is absent, the old heuristic path still degrades safely

### T-014 Release Evidence Route Preference

Goal:

- Confirm release-related incident threads prefer release notes over generic documents when both are available.

Input:

- Thread discussing a deploy, rollback, or release regression
- Knowledge source containing both release notes and general SOP documents

Expected result:

- Retrieval returns release-note evidence ahead of generic documents
- The top citation in the rendered incident reply comes from the release route
- The behavior stays deterministic across repeated runs

### T-015 Weak Evidence Filtering

Goal:

- Confirm low-signal keyword overlap does not bypass insufficient-context safeguards.

Input:

- Ambiguous thread with only broad shared terms
- Knowledge source containing weakly related documents but no strong route match

Expected result:

- Retrieval returns no strong citation candidates, or only citations above the configured threshold
- The analysis layer still emits `insufficient_context` when no reliable evidence remains
- The system does not convert a weak hit into a confident diagnosis

### T-016 Pending Action Persistence

Goal:

- Confirm summarize-thread success replies can persist reviewable task-sync and postmortem actions before execution.

Input:

- A summarize-thread trigger with a successful structured summary

Expected result:

- The thread-scoped action queue stores pending task-sync and postmortem actions
- The user-facing reply includes action ids and approval commands
- If the reply send fails, the just-created pending actions are discarded

### T-017 Approval-Backed Incident Action Execution

Goal:

- Confirm explicit approval commands execute only the targeted action and write the result back to the same thread.

Input:

- An existing pending action such as `A1`
- A thread message containing `批准动作 A1`

Expected result:

- The system resolves the action only within the current thread
- Task-sync actions execute with `confirmed = true`
- Postmortem actions write the rendered draft back to the same thread
- Repeated approval does not create duplicate side effects

## 5. Manual Verification Checklist

Before calling P0 usable, confirm manually:

- The bot responds only when explicitly triggered
- The first reply acknowledges analysis start or directly returns a result
- The result format matches the product wording in the PRD
- Evidence-backed results show citations clearly
- Low-evidence cases clearly state what is missing
- Failure cases do not produce confusing raw errors

## 6. Exit Criteria For P0

P0 should not be marked ready unless:

- All `Must Pass For P0` cases succeed
- At least one happy path and one insufficient-context path are demonstrated with fixtures
- The reply format is reviewed from a real user-reading perspective

If any of these are missing, the P0 loop is not fully verified.
