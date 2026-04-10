# Decision Log

## 1. Purpose

This file records high-value project decisions, the reason they were made, and what would justify reopening them.

Use it to prevent future sessions from relitigating already-closed questions.

## 2. Entry Template

Copy this format for new confirmed decisions.

### DEC-XXX

- Date:
- Status: proposed / confirmed / superseded
- Decision:
- Why:
- Alternatives considered:
- Impacted files:
  - 
- Revisit when:

## 3. Confirmed Decisions

### DEC-001

- Date: 2026-04-10
- Status: confirmed
- Decision: `P0` uses explicit manual trigger only.
- Why: automatic incident detection adds ambiguity and integration cost too early.
- Alternatives considered:
  - automatic detection from group messages
  - mixed manual and automatic trigger in first release
- Impacted files:
  - `rd-incident-ai-assistant-prd.md`
  - `feature-list.md`
  - `test-cases.md`
  - `api-contracts.md`
- Revisit when:
  - the manual-trigger loop has passed acceptance and real usage shows repeated trigger friction

### DEC-002

- Date: 2026-04-10
- Status: confirmed
- Decision: `P0` does not integrate Jira.
- Why: Jira is useful for later workflow closure, but it is not required to prove the core product loop.
- Alternatives considered:
  - read-only Jira context in `P0`
  - full Jira task sync in `P0`
- Impacted files:
  - `rd-incident-ai-assistant-prd.md`
  - `tech-spec.md`
  - `api-contracts.md`
  - `task-board.json`
- Revisit when:
  - `P1` planning starts or the product needs external task closure to remain credible

### DEC-003

- Date: 2026-04-10
- Status: confirmed
- Decision: the first implementation path uses local knowledge documents only.
- Why: local documents are enough to validate source-aware reply behavior without early connector cost.
- Alternatives considered:
  - Jira-backed knowledge
  - multiple external knowledge connectors from day one
- Impacted files:
  - `tech-spec.md`
  - `schema.md`
  - `feature-list.md`
  - `task-board.json`
- Revisit when:
  - the basic retrieval path is stable and new evidence sources are required

### DEC-004

- Date: 2026-04-10
- Status: confirmed
- Decision: one thread serves one primary task, and every new session is stateless.
- Why: this project is being developed through long-running AI-assisted sessions, so recoverability is more important than thread continuity.
- Alternatives considered:
  - continue long mixed-purpose threads
  - rely on chat memory instead of file-based reconstruction
- Impacted files:
  - `agent.md`
  - `session-playbook.md`
  - `progress.md`
  - `task-board.json`
- Revisit when:
  - version-control workflow and implementation maturity make recovery materially safer

### DEC-005

- Date: 2026-04-10
- Status: confirmed
- Decision: agent self-improvement follows `session evidence -> skill candidate -> approved canonical docs`.
- Why: the project needs accumulation of verified patterns without letting the AI silently rewrite scope or contracts.
- Alternatives considered:
  - auto-updating prompts and specs after each session
  - keeping all lessons only in chat history
- Impacted files:
  - `evolution-policy.md`
  - `agent.md`
  - `progress.md`
- Revisit when:
  - a stable repeatable workflow exists for promoting candidate skills into a maintained skill library
