# P0 Technical Specification

## 1. Scope

This document defines the minimum implementation spec for P0.

P0 goal:

`A user manually triggers analysis in a Feishu thread, and the system replies in the same thread with a structured summary plus source citations.`

P0 does not include:

- automatic incident detection
- Jira integration
- external task sync
- multi-turn memory as a hard requirement
- hybrid retrieval, reranking, or advanced retrieval optimization

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

Target layout for the first runnable code pass:

```text
app/
  main.py
  api/
    feishu.py
  clients/
    feishu_client.py
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
    reply_renderer.py
tests/
  fixtures/
  test_health.py
  test_command_parser.py
  test_analysis_contracts.py
data/
  knowledge/
```

Module ownership:

- `api/`: inbound HTTP routes only
- `clients/`: outbound vendor or LLM calls
- `core/`: config and logging primitives
- `models/`: internal contracts defined by `schema.md`
- `services/`: business orchestration and transformations
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
- `MAX_THREAD_MESSAGES`
- `MAX_KNOWLEDGE_HITS`

Default behavior:

- `KNOWLEDGE_DIR` defaults to `data/knowledge`
- `LLM_TIMEOUT_SECONDS` defaults to `30`
- `MAX_THREAD_MESSAGES` defaults to `50`
- `MAX_KNOWLEDGE_HITS` defaults to `5`

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

The route must hand off a normalized `AnalysisRequest` object to the service layer.

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

One P0 request should move through the system in this order:

1. Feishu callback reaches `/api/feishu/events`
2. The route validates and normalizes the event
3. The command parser extracts the user intent
4. The thread reader loads the current thread or message context
5. The knowledge service loads or queries local knowledge documents
6. The analysis service builds the LLM input and requests a structured summary
7. The reply renderer converts the structured result into user-facing Feishu text
8. The Feishu client posts the reply back to the same discussion context

The route layer should not contain business logic beyond validation and normalization.

## 8. Knowledge Source Rules

P0 knowledge source is local and controlled.

Requirements:

- read local Markdown or text documents only
- support a simple matching strategy good enough for P0
- return a bounded set of citation candidates
- preserve source labels so the reply can cite them

P0 does not require:

- vector search
- reranking
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

- local knowledge files under `data/knowledge`
- transient in-memory request objects
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

This P0 spec does not define:

- automatic incident detection
- same-thread follow-up memory
- Jira integration
- task sync
- advanced retrieval
- postmortem generation

Those belong to later milestones and should not be pulled into P0 by default.
