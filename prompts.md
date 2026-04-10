# P0 Prompt Definitions

## 1. Purpose

This document defines the prompt contracts for P0.

It exists so future coding sessions do not keep inventing new prompt styles or output formats.

P0 only needs prompts for:

- structured incident summary
- insufficient-context handling

Not in scope for P0:

- query rewriting
- summary compression
- postmortem generation
- task planning

## 2. Prompt Design Rules

All P0 prompts must follow these rules:

- stay grounded in the current thread context and available citations
- prefer uncertainty over fabricated certainty
- produce structured output aligned with `schema.md`
- never claim evidence that is not present in thread content or citation inputs
- keep user language concise and readable in a Feishu thread

## 3. System Prompt Skeleton

Base system prompt:

```text
你是一个研发故障讨论助手。

你的任务不是替用户拍板最终结论，而是基于当前飞书讨论和提供的参考依据，输出一份结构化、可追溯的分析摘要。

你必须遵守以下规则：
1. 只能基于输入中的讨论内容和参考依据作答。
2. 如果信息不足，明确写出缺失信息，不要硬凑结论。
3. 如果依据不足，不要给出高置信度判断。
4. 输出必须符合指定 JSON 结构。
5. 所有引用必须来自输入中的 references。
```

## 4. User Prompt Skeleton

```text
请基于以下飞书讨论内容和参考依据，输出一份结构化分析摘要。

讨论内容：
{{thread_context}}

参考依据：
{{references}}

请输出 JSON，字段必须包含：
- status
- confidence
- current_assessment
- known_facts
- impact_scope
- next_actions
- citations
- missing_information
```

## 5. Structured Summary Prompt Variant

Use this variant for the main happy path.

Additional instruction:

```text
如果已有信息足以形成当前判断，请用谨慎但明确的语言总结“当前判断”。
如果影响范围不明确，也必须明确说明不确定性。
```

Expected output target:

- `status = success` or `status = insufficient_context`
- valid JSON
- fields aligned with `schema.md`

## 6. Insufficient-Context Prompt Variant

Use this behavior when:

- thread context is too weak
- references are empty or irrelevant
- the service explicitly chooses the safe degraded path

Additional instruction:

```text
当前信息不足，请不要给出强结论。
你的重点是：
1. 总结当前已知事实
2. 明确指出缺少哪些信息
3. 给出下一步建议
4. 保持低置信度
```

Expected output target:

- `status = insufficient_context`
- `confidence = low`
- non-empty `missing_information`

## 7. Temporary Failure User Message

This is not an LLM prompt. It is the fallback user-facing message template when the LLM path fails.

Template:

```text
状态：
本次分析未完整完成

当前已知：
{{known_facts}}

缺少信息：
{{missing_information}}

建议：
请稍后重试，或补充更多上下文后再次触发。
```

## 8. Prompt Input Contracts

The prompt builder should receive:

- normalized thread messages
- citation candidates
- optional analysis mode: `analyze_incident`, `summarize_thread`, `rerun_analysis`

The prompt builder should not receive:

- raw vendor payloads
- transport metadata unrelated to the user-visible analysis
- hidden implementation details not useful to the model

## 9. Prompt Stability Rules

When refining prompts later:

- do not change output fields without updating `schema.md`
- do not add free-form sections that break reply rendering
- do not add hidden assumptions about unsupported integrations

Prompt changes must preserve:

- explicit uncertainty
- source awareness
- stable JSON shape
