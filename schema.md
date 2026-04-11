# P0 Schemas

## 1. Goal

This document defines the minimum data contracts needed to implement P0 safely and consistently.

P0 favors explicit, simple contracts over flexible but ambiguous payloads.

## 2. Normalized Analysis Request

Internal object produced after callback validation and command parsing.

```json
{
  "trigger_command": "analyze_incident",
  "chat_id": "oc_xxx",
  "thread_id": "omt_xxx",
  "trigger_message_id": "om_xxx",
  "user_id": "ou_xxx",
  "user_display_name": "Alice",
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

Field rules:

- `trigger_command`: required enum
- `chat_id`: required string
- `thread_id`: required string when a thread exists; otherwise use the trigger message id as the thread anchor
- `trigger_message_id`: required string
- `user_id`: required string
- `user_display_name`: optional string
- `thread_messages`: required non-empty array
- `follow_up_context`: optional object for summarize/rerun flows

Supported `trigger_command` values in P0:

- `analyze_incident`
- `summarize_thread`
- `rerun_analysis`

## 2.1 Follow-Up Context

Current follow-up requests may also carry:

```json
{
  "previous_summary": "当前判断：支付服务异常可能与最近发布有关。",
  "new_messages": [
    {
      "message_id": "om_2",
      "sender_name": "Alice",
      "sent_at": "2026-04-10T01:05:00+08:00",
      "text": "补充信息：回滚后错误率继续下降"
    }
  ],
  "source": "memory"
}
```

Field rules:

- `previous_summary`: optional string
- `new_messages`: required array, may be empty
- `source`: optional enum: `memory` or `heuristic`

## 3. Thread Message Item

```json
{
  "message_id": "om_1",
  "sender_name": "Alice",
  "sent_at": "2026-04-10T01:00:00+08:00",
  "text": "we rolled back payment-api and error rate is dropping"
}
```

Field rules:

- `message_id`: required string
- `sender_name`: required string, fallback `"Unknown"`
- `sent_at`: required ISO-8601 string
- `text`: required string, trimmed, may not be empty

## 4. Knowledge Citation

```json
{
  "source_type": "knowledge_doc",
  "label": "支付服务故障处理 SOP",
  "source_uri": "data/knowledge/payment-sop.md",
  "snippet": "排查支付 5xx 时，优先确认最近发布和数据库连接池状态。"
}
```

Field rules:

- `source_type`: required enum: `thread_message` or `knowledge_doc`
- `label`: required string
- `source_uri`: required string
- `snippet`: required string

## 5. Structured Summary

This is the primary P0 output contract.

```json
{
  "status": "success",
  "confidence": "medium",
  "current_assessment": "当前更像是一次发布后导致的支付服务异常，仍需补充日志确认。",
  "known_facts": [
    "支付服务出现 5xx 告警",
    "线程中提到已执行回滚",
    "错误率有下降迹象"
  ],
  "impact_scope": "影响支付服务相关请求，具体用户范围仍待确认。",
  "next_actions": [
    "补充错误日志",
    "确认最近一次发布内容",
    "观察回滚后的错误率变化"
  ],
  "citations": [
    {
      "source_type": "thread_message",
      "label": "飞书线程消息",
      "source_uri": "feishu://message/om_1",
      "snippet": "payment service 5xx spike"
    }
  ],
  "missing_information": [
    "错误日志",
    "最近发布详情"
  ]
}
```

Field rules:

- `status`: required enum: `success`, `insufficient_context`, `temporary_failure`
- `confidence`: required enum: `low`, `medium`, `high`
- `current_assessment`: required string
- `known_facts`: required array of strings, may be empty
- `impact_scope`: required string
- `next_actions`: required array of strings, may be empty
- `citations`: required array of `KnowledgeCitation`, may be empty
- `missing_information`: required array of strings, may be empty

P0 formatting constraints:

- `current_assessment` must not be an empty string
- `impact_scope` must never be omitted; when unknown, use a clear uncertainty sentence instead of `null`
- `known_facts`, `next_actions`, `citations`, and `missing_information` must always exist, even when empty
- do not use empty string placeholders for lists

## 6. Insufficient Context Summary

Used when the system cannot support a strong conclusion.

```json
{
  "status": "insufficient_context",
  "confidence": "low",
  "current_assessment": "当前信息不足，暂时无法判断完整原因和影响范围。",
  "known_facts": [
    "线程中存在异常讨论"
  ],
  "impact_scope": "当前无法可靠判断。",
  "next_actions": [
    "补充错误日志",
    "补充最近变更信息"
  ],
  "citations": [],
  "missing_information": [
    "错误日志",
    "变更记录"
  ]
}
```

## 7. Temporary Failure Reply

Used when analysis fails but a user-visible reply must still be sent.

```json
{
  "status": "temporary_failure",
  "headline": "本次分析未完整完成",
  "known_facts": [
    "已读取当前线程"
  ],
  "missing_information": [
    "完整分析结果"
  ],
  "citations": [],
  "retry_hint": "请稍后重试，或补充更多上下文后再次触发。"
}
```

Field rules:

- `status`: fixed value `temporary_failure`
- `headline`: required string
- `known_facts`: required array of strings, may be empty
- `missing_information`: required array of strings, may be empty
- `citations`: required array of `KnowledgeCitation`, may be empty
- `retry_hint`: required string

## 8. Feishu User-Facing Reply Contract

The renderer converts either a `StructuredSummary` or a `TemporaryFailureReply` into user-facing text.

Minimum successful reply layout:

```text
当前判断：
已知事实：
- ...

影响范围：
...

下一步建议：
- ...

参考来源：
- ...
```

Minimum failure reply layout:

```text
状态：
本次分析未完整完成

当前已知：
- ...

缺少信息：
- ...

建议：
请稍后重试，或补充更多上下文后再次触发。
```

## 9. Knowledge Document Metadata

P0 may use file-backed knowledge documents without a database.

Optional metadata contract for each local knowledge item:

```json
{
  "doc_id": "payment-sop",
  "title": "支付服务故障处理 SOP",
  "path": "data/knowledge/payment-sop.md",
  "tags": [
    "payment",
    "incident"
  ]
}
```

Field rules:

- `doc_id`: required string
- `title`: required string
- `path`: required string
- `tags`: optional array of strings

## 10. Analysis Result Record

Even without a database, tests and logs should be able to refer to a normalized result record.

```json
{
  "request_id": "req_20260410_0001",
  "trigger_command": "analyze_incident",
  "chat_id": "oc_xxx",
  "thread_id": "omt_xxx",
  "result_status": "success",
  "summary": {
    "status": "success",
    "confidence": "medium",
    "current_assessment": "..."
  }
}
```

Field rules:

- `request_id`: required string
- `trigger_command`: required enum
- `chat_id`: required string
- `thread_id`: required string
- `result_status`: required enum aligned with `StructuredSummary.status`
- `summary`: required object for successful and insufficient-context paths

## 10.1 Memory Models

The implemented foundation now includes explicit local thread memory.

Thread memory example:

```json
{
  "schema_version": 1,
  "last_summary_text": "当前判断：支付服务异常可能与最近发布有关。",
  "last_summary_message_id": "om_bot_1",
  "last_processed_message_id": "om_3",
  "last_processed_at": "2026-04-10T01:06:00+08:00",
  "last_trigger_command": "analyze_incident",
  "last_summary_status": "success",
  "updated_at": "2026-04-10T01:07:00+08:00",
  "known_facts": [
    "已执行回滚"
  ],
  "open_questions": [
    "详细错误日志"
  ]
}
```

Field rules:

- `schema_version`: required integer
- `last_summary_text`: optional string
- `last_summary_message_id`: optional string
- `last_processed_message_id`: optional string
- `last_processed_at`: optional ISO-8601 string
- `last_trigger_command`: optional trigger enum
- `last_summary_status`: optional result-status enum
- `updated_at`: required ISO-8601 string
- `known_facts`: required array of strings
- `open_questions`: required array of strings

## 11. Null And Empty Rules

P0 uses these conventions consistently:

- Prefer explicit fallback text over `null` for user-visible strings
- Prefer empty arrays over missing list fields
- Do not omit required fields
- Do not encode missing information as empty strings

These rules exist so Codex does not invent inconsistent output shapes across modules.
