# P0 API Contracts

## 1. Purpose

This document defines the external and adapter-facing contracts needed for P0.

It exists to reduce guessing when implementing:

- Feishu callback handling
- Feishu reply sending
- Feishu thread loading
- LLM invocation

Current scope:

- Feishu: active in P0
- LLM: active in P0
- Jira: reserved only, not active in P0

## 2. Contract Strategy

P0 should not wire business logic directly to vendor payloads everywhere.

Use this layering:

- external vendor payload
- adapter normalization
- internal contract from `schema.md`

This keeps future API changes local to one adapter.

## 3. Feishu Contracts

### 3.1 Inbound Callback

Purpose:

- Receive event subscription callbacks from Feishu.

Current local route:

- `POST /api/feishu/events`

Expected callback categories in P0:

- URL verification
- message or thread-related event with explicit manual trigger

Local adapter output:

- `verification_request`
- `message_event`
- `ignored_event`

Required normalized fields for a message event:

- `chat_id`
- `message_id`
- `thread_id` when available
- `sender_id`
- `sender_name` when available
- `message_text`
- `mentions_bot`
- `event_time`

Failure handling:

- malformed callback payload -> log and return safe ignore
- unsupported event type -> safe ignore
- missing minimal message fields -> safe ignore

### 3.2 URL Verification Contract

The callback layer must support Feishu platform verification before message handling.

Local expected behavior:

- detect verification payload
- return the required verification response immediately
- do not invoke analysis logic

Implementation note:

- keep platform verification isolated inside the route or adapter layer

### 3.3 Manual Trigger Parsing Contract

Supported P0 trigger phrases:

- `分析一下这次故障`
- `帮我总结当前结论`
- `基于最新信息重试`

Local parser contract:

Input:

```json
{
  "message_text": "@机器人 分析一下这次故障",
  "mentions_bot": true
}
```

Output:

```json
{
  "accepted": true,
  "trigger_command": "analyze_incident"
}
```

Or:

```json
{
  "accepted": false,
  "reason": "unsupported_message"
}
```

### 3.4 Thread Loading Contract

Purpose:

- Read the current discussion context that should be analyzed.

P0 local adapter contract:

Input:

```json
{
  "chat_id": "oc_xxx",
  "message_id": "om_xxx",
  "thread_id": "omt_xxx"
}
```

Output:

```json
{
  "thread_messages": [
    {
      "message_id": "om_1",
      "sender_name": "AlertBot",
      "sent_at": "2026-04-10T01:00:00+08:00",
      "text": "payment service 5xx spike"
    }
  ]
}
```

If Feishu thread retrieval is partially unavailable:

- return what can be read
- allow the service layer to produce an insufficient-context result

### 3.5 Reply Sending Contract

Purpose:

- Send the final result back to the original discussion context in Feishu.

Local adapter input:

```json
{
  "chat_id": "oc_xxx",
  "thread_id": "omt_xxx",
  "trigger_message_id": "om_xxx",
  "reply_text": "当前判断：..."
}
```

Local adapter output:

```json
{
  "success": true,
  "reply_message_id": "om_reply_xxx"
}
```

Or:

```json
{
  "success": false,
  "error_code": "reply_failed",
  "error_message": "feishu_send_failed"
}
```

Reply failure behavior in P0:

- log the failure
- do not leak raw vendor errors to the user
- preserve a user-safe fallback path where possible

### 3.6 Feishu Official API References

Current official references used for this draft:

- Send message: [Feishu Open Platform - Send message](https://open.feishu.cn/document/server-docs/im-v1/message/create)
- Get chat history: [Feishu Open Platform - Get chat history](https://open.feishu.cn/document/server-docs/im-v1/message/list)

Note:

- Event subscription details should be confirmed against the Feishu event subscription documentation when wiring the live callback.
- Exact vendor payloads may vary; internal adapter contracts in this document are the local source of truth for implementation.

## 4. LLM Contracts

### 4.1 Provider Scope

P0 uses an OpenAI-compatible LLM interface.

Current required configuration:

- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`

The adapter should hide vendor-specific HTTP details from business modules.

### 4.2 LLM Request Contract

Local adapter input:

```json
{
  "system_prompt": "You are an incident discussion assistant...",
  "user_prompt": "Thread context ...",
  "response_mode": "structured_summary"
}
```

Local adapter output:

```json
{
  "success": true,
  "raw_text": "{ ... structured summary json ... }"
}
```

Or:

```json
{
  "success": false,
  "error_code": "llm_timeout",
  "error_message": "request timed out"
}
```

### 4.3 Structured Output Rule

For P0, structured output should be constrained by prompt-format JSON output, then validated against `schema.md`.

P0 does not require:

- function calling
- tool calling
- multi-step agent planning

Implementation rule:

- the LLM may return text
- the service layer must parse and validate it into the `StructuredSummary` contract
- invalid output must degrade into the temporary-failure path

### 4.4 Timeout And Retry Rule

P0 default:

- one request attempt
- timeout controlled by `LLM_TIMEOUT_SECONDS`
- no hidden multi-retry loop in business logic

If the request times out:

- produce a user-safe temporary-failure reply
- do not silently rerun expensive analysis

## 5. Jira Contract Placeholder

Jira is not part of P0.

This section exists only to prevent accidental P0 scope creep.

Future candidate capabilities:

- query existing issue by link or key
- create external task from a reviewed todo draft

Not allowed in P0:

- active Jira API integration
- automatic issue creation
- task sync as a dependency for the main user flow

## 6. Adapter Error Categories

Use these local error categories when vendor calls fail:

- `verification_failed`
- `unsupported_event`
- `callback_parse_failed`
- `thread_load_failed`
- `reply_failed`
- `llm_timeout`
- `llm_invalid_response`
- `llm_request_failed`

These are local application categories, not vendor-native error codes.

## 7. Implementation Rule

When vendor and local contracts differ:

- preserve the vendor payload only inside the adapter layer
- normalize immediately into local contracts
- make business services depend only on local contracts
