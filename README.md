# stackpilot

`stackpilot` is evolving from a Feishu incident summarizer into an `evolving workflow agent` for R&D teams.

The current implemented baseline already covers:

- Feishu thread ingestion
- explicit thread memory for same-thread continuity
- deterministic planner-router-ranker evidence retrieval
- source-aware incident analysis
- follow-up summary output
- task draft generation
- postmortem draft generation
- action proposal queue with approval commands
- append-only evidence recording and draft skill candidates
- AI code review from inline diff or GitHub PR input
- approval-backed GitHub draft review publishing
- review focus routing with user preference memory
- org-level review default focus shaping
- team-style postmortem draft and rendering shaping
- explicit finding adoption signals and review-focus draft skill candidates

The next product direction is no longer just "summarize one thread". It is:

- `Incident workflow`: analyze, cite evidence, draft actions, and close the loop with approval
- `Growth kernel`: remember team habits, record interactions, mine repeatable skills, and evolve under audit
- `AI code review`: ingest diffs, apply team review policy, generate structured findings, and learn from acceptance signals

## Current Position

Think of the repository in two layers:

1. `Implemented foundation`
   Feishu-first incident discussion analysis plus manual AI code review, both with structured replies, source-aware evidence, approval-backed actions, tenant-scoped org conventions, and a draft-only growth kernel.
2. `Planned platform`
   A controlled workflow agent that supports incident handling and AI code review on top of shared memory, retrieval, approval, and audit capabilities.

## Key Docs

- [Product PRD](./rd-incident-ai-assistant-prd.md)
- [Evolution Architecture](./evolving-agent-architecture.md)
- [Feature List](./feature-list.md)
- [Technical Spec](./tech-spec.md)
- [Schema](./schema.md)

## Local Setup

Windows PowerShell:

```powershell
.\scripts\bootstrap.ps1
```

## Run The App

```powershell
.\scripts\dev.ps1
```

The service starts on [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Run Tests

```powershell
.\scripts\test.ps1
```

## Current Repository Layout

- `app/api`: inbound routes
- `app/clients`: external service clients
- `app/core`: configuration and logging
- `app/models`: shared contracts
- `app/prompts`: prompt templates
- `app/services`: workflow orchestration services
- `app/services/kernel`: shared memory, org convention shaping, and future growth-kernel services
- `app/services/review`: AI code review parsing, normalization, rendering, and publish services
- `app/services/retrieval`: deterministic retrieval pipeline components
- `data/knowledge`: local controlled knowledge sources
- `data/actions`: local persisted pending-action queue
- `data/records`: append-only workflow evidence and audit logs
- `data/memory`: local persisted workflow memory
- `data/skills`: draft skill candidates and lifecycle metadata
- `tests`: smoke and contract coverage

## Scope Guardrails

The new roadmap does not mean "let the agent freely change itself".

Still out of scope by default:

- autonomous source-code rewriting of the main product
- silent schema or policy mutation
- unapproved external task execution
- generic chatbot expansion
- multi-agent architecture for its own sake
