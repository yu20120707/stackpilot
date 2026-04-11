# Foundation Technical Specification

## 1. Scope

This document defines the current foundation implementation shape for the repository.

Original P0 goal:

`A user manually triggers analysis in a Feishu thread, and the system replies in the same thread with a structured summary plus source citations.`

The codebase still preserves that foundation, but the implemented baseline now also includes:

- same-thread follow-up support
- conclusion summary and todo draft output
- postmortem draft generation
- confirmation-gated task-sync contract
- explicit local thread memory for workflow continuity
- deterministic retrieval planning, routing, and evidence ranking
- pending incident action persistence with approval-backed execution
- append-only evidence recording and draft skill candidate generation
- manual AI code review from inline diff or GitHub PR input
- deterministic diff normalization and structured draft review findings
- approval-backed GitHub draft review publishing
- review focus routing with repeated-request user preference memory
- explicit review finding feedback recording and review-memory persistence
- org-level review default focus shaping
- team-style postmortem draft and rendering shaping
- approved canonical convention docs under the knowledge layer

Still out of scope for the current foundation:

- automatic incident detection
- autonomous code modification
- unapproved external execution
- generic multi-agent orchestration

## 2. Implementation Draft

Unless explicitly changed later, the implementation draft assumes:

- Language: Python 3.11
- Web framework: FastAPI
- Validation models: Pydantic v2
- HTTP client: `httpx`
- Package manager: `uv`
- Tests: `pytest`

Rationale:

- This stack is fast to scaffold
- It is well suited to webhook-style backend work
- It keeps P0 lightweight and easy to iterate on

## 3. Repository Layout

Current layout baseline:

```text
app/
  main.py
  api/
    feishu.py
  clients/
    feishu_client.py
    github_review_client.py
    llm_client.py
  core/
    config.py
    logging.py
  models/
    contracts.py
  prompts/
    analysis_prompt.md
  services/
    command_parser.py
    thread_reader.py
    knowledge_base.py
    analysis_service.py
    incident_action_service.py
    postmortem_renderer.py
    postmortem_service.py
    reply_renderer.py
    skill_miner.py
    skill_registry.py
    task_sync_service.py
    workflow_router.py
    kernel/
      action_queue_service.py
      audit_log_service.py
      canonical_convention_service.py
      interaction_recorder.py
      memory_service.py
      org_convention_service.py
    review/
      diff_reader.py
      flow.py
      input_parser.py
      preference_service.py
      policy_service.py
      publish_service.py
      renderer.py
      service.py
    retrieval/
      planner.py
      router.py
      ranker.py
      service.py
tests/
  fixtures/
  test_health.py
  test_command_parser.py
  test_analysis_contracts.py
data/
  actions/
  knowledge/
  memory/
  records/
  skills/
```

Module ownership:

- `api/`: inbound HTTP routes only
- `clients/`: outbound vendor or LLM calls
- `core/`: config and logging primitives
- `models/`: internal contracts defined by `schema.md`
- `services/`: business orchestration and transformations
- `services/kernel/`: shared workflow memory, org convention shaping, and future growth-kernel primitives
- `services/retrieval/`: deterministic evidence planning, routing, and ranking
- `prompts/`: prompt templates only

## 4. Environment Variables

Required for P0:

- `APP_ENV`
- `PORT`
- `LOG_LEVEL`
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `KNOWLEDGE_DIR`

Optional for P0:

- `FEISHU_ENCRYPT_KEY`
- `FEISHU_VERIFICATION_TOKEN`
- `LLM_TIMEOUT_SECONDS`
- `GITHUB_API_BASE_URL`
- `GITHUB_TOKEN`
- `GITHUB_TIMEOUT_SECONDS`
- `MAX_THREAD_MESSAGES`
- `MAX_KNOWLEDGE_HITS`
- `ACTION_DIR`
- `MEMORY_DIR`
- `RECORDS_DIR`
- `SKILLS_DIR`

Default behavior:

- `KNOWLEDGE_DIR` defaults to `data/knowledge`
- `LLM_TIMEOUT_SECONDS` defaults to `30`
- `GITHUB_API_BASE_URL` defaults to `https://api.github.com`
- `GITHUB_TIMEOUT_SECONDS` defaults to `20`
- `MAX_THREAD_MESSAGES` defaults to `50`
- `MAX_KNOWLEDGE_HITS` defaults to `5`
- `ACTION_DIR` defaults to `data/actions`
- `MEMORY_DIR` defaults to `data/memory`
- `RECORDS_DIR` defaults to `data/records`
- `SKILLS_DIR` defaults to `data/skills`

## 5. External Routes

### 5.1 Health Route

- Method: `GET`
- Path: `/healthz`
- Purpose: runtime liveness check

Success response:

```json
{
  "status": "ok"
}
```

### 5.2 Feishu Callback Route

- Method: `POST`
- Path: `/api/feishu/events`
- Purpose: receive Feishu event subscription callbacks

Route responsibilities:

- handle platform URL verification handshake
- acknowledge supported message events
- normalize only supported manual trigger requests
- ignore unrelated messages safely

P0 supported manual commands:

- `分析一下这次故障`
- `帮我总结当前结论`
- `基于最新信息重试`
- `批准动作 A1`
- `帮我 review 这个 PR https://github.com/org/repo/pull/123`
- `审一下这个 diff` with inline patch content
- `采纳建议 F1`
- `忽略建议 F2`

The route must hand off a normalized trigger event to a workflow router, which then dispatches either incident analysis or AI code review to the service layer.

## 6. Callback Handling Rules

P0 only responds when all of the following are true:

- the incoming event is a message or thread-related callback supported by the integration
- the message is in an allowed group or thread context
- the bot is explicitly mentioned or the message matches a supported trigger pattern

P0 should ignore:

- direct messages unless explicitly enabled later
- non-text content without usable text fallback
- ordinary group chatter without a supported manual trigger

## 7. Request Flow

One incident-analysis request currently moves through the system in this order:

1. Feishu callback reaches `/api/feishu/events`
2. The route validates and normalizes the event
3. The command parser extracts the user intent
4. The workflow router dispatches incident-analysis commands to the incident live flow
5. The thread reader loads the current thread or message context
6. The knowledge service loads local knowledge documents and approved tenant-scoped canonical convention docs when available
7. The analysis service builds the LLM input and requests a structured summary
8. For summarize-thread success cases, the incident-action service prepares task-sync and postmortem proposals and stores them in the action queue
9. When tenant org conventions exist, postmortem generation and rendering apply the resolved effective style, and the pending action stores a snapshot so later write-back does not drift if mutable org memory changes
10. The reply renderer converts the structured result into user-facing Feishu text
11. The Feishu client posts the reply back to the same discussion context
12. The thread memory service persists the latest successful structured summary state

One AI-code-review request currently moves through the system in this order:

1. Feishu callback reaches `/api/feishu/events`
2. The route validates and normalizes the event
3. The command parser extracts an explicit code-review trigger
4. The workflow router dispatches the request to the review flow
5. The review input parser extracts either an inline patch or a GitHub PR URL
6. For GitHub PR input, the GitHub client attempts to fetch the PR diff
7. The diff reader normalizes changed files and hunks into a stable review request
8. The review policy service selects relevant policy citations from general knowledge plus approved tenant-scoped canonical review docs
9. The review preference service resolves focus areas in this order: explicit user request, remembered user preference, approved canonical defaults, mutable org defaults, then safe fallback defaults
10. The review service prompts the LLM for a structured draft review
11. The review renderer returns a Feishu draft reply, and GitHub publish is queued as a pending action when applicable
12. The review memory service persists the latest review state and finding ids for the thread
13. Users can approve the pending publish action from the same thread to post a draft comment back to GitHub
14. Users can explicitly mark findings as accepted or ignored from the same thread, and the interaction recorder stores those feedback signals for later mining

Approval-backed incident actions move through this order:

1. Feishu callback accepts `批准动作 A1`
2. The command parser extracts the action id from the thread message
3. The incident-action service resolves the pending action from the thread-scoped queue
4. The selected task-sync or postmortem action executes under explicit approval
5. The result is written back to the same thread

Growth-kernel recording currently moves through this order:

1. A visible analysis reply or approval result is sent successfully
2. The interaction recorder appends thread-scoped evidence and tenant-scoped audit summaries
3. The skill miner evaluates repeated successful approval-loop patterns for the tenant
4. If the threshold is met, a draft skill candidate is written under `data/skills`

The route layer should not contain business logic beyond validation and normalization.

## 8. Knowledge Source Rules

P0 knowledge source is local and controlled.

Requirements:

- read local Markdown or text documents only
- read approved tenant-scoped canonical convention docs from `data/knowledge/canonical/<tenant>/*.canonical.json`
- support deterministic planning, routing, ranking, and bounded second-pass retrieval
- return a bounded set of citation candidates
- preserve source labels so the reply can cite them
- filter weak evidence so low-signal hits do not bypass insufficient-context safeguards
- never expose another tenant's canonical docs in the current request scope

P0 does not require:

- vector search
- document sync pipelines
- database-backed metadata

## 9. Structured Summary Rules

P0 must produce a structured result matching `schema.md`.

Required user-facing sections:

- current assessment
- known facts
- impact scope
- next actions
- citations

When evidence is weak:

- do not fabricate a strong conclusion
- populate `missing_information`
- lower confidence
- still return a usable response object

## 10. User-Visible Failure Behavior

P0 must keep user-visible failures simple and consistent.

If analysis cannot complete fully, the reply should still contain:

- a short status line
- what was understood so far
- what information is missing
- any usable citations that were found
- a retry hint

Do not expose raw stack traces or vendor-specific error text in Feishu replies.

## 11. Persistence Strategy

P0 has no mandatory database requirement.

Allowed in P0:

- local action queue files under `data/actions`
- local knowledge files under `data/knowledge`
- local approved canonical convention docs under `data/knowledge/canonical`
- local thread memory files under `data/memory`
- local tenant org memory files under `data/memory/<tenant>/org.json`
- local evidence and audit files under `data/records`
- local skill candidate files under `data/skills`
- application logs

Not required in P0:

- Redis
- PostgreSQL
- task tables
- async job queues

If later persistence is added, it must not change the external callback or reply contracts defined in this document and `schema.md`.

## 12. Testing Minimum

P0 should be considered implementable only if the following can be tested:

- health route responds
- supported manual commands are parsed correctly
- unsupported messages are ignored
- one fixture thread can produce a structured summary
- one insufficient-context fixture produces a safe degraded reply

## 13. Out Of Scope For This Spec

This foundation spec still does not define:

- automatic incident detection
- autonomous task execution without approval
- external vector-backed retrieval infrastructure
- automatic code fixing or commit submission

Those belong to later milestones and should not be pulled into the implemented foundation by default.
