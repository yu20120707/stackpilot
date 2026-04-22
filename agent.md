# Agent Working Contract

## 1. Purpose

This file defines the working harness for this repository so future AI coding sessions stay recoverable and scoped.

Project target:

`A controlled workflow agent for R&D teams, starting from Feishu incident analysis and expanding into auditable growth and AI-assisted code review.`

Current implementation baseline:

`manual Feishu trigger -> thread context -> evidence lookup -> structured incident summary -> reply`

Planned platform direction:

`shared memory + retrieval + approval + audit + skills -> incident workflow + AI code review workflow`

This project is still not a generic multi-agent playground.

## 2. Canonical Sources

Every new session must treat itself as stateless and rebuild context from files, not memory.

Start by running `.\init.ps1`.

Then read in this order before doing implementation:

1. `rd-incident-ai-assistant-prd.md`
2. `evolving-agent-architecture.md`
3. `tech-spec.md`
4. `schema.md`
5. `api-contracts.md`
6. `prompts.md`
7. `feature-list.md`
8. `test-cases.md`
9. `evolution-policy.md`
10. `session-playbook.md`
11. `decision-log.md`
12. `task-board.json`
13. `progress.md`

If files conflict, resolve them in this order of authority:

1. `rd-incident-ai-assistant-prd.md`
2. `evolving-agent-architecture.md`
3. `tech-spec.md`
4. `schema.md`
5. `api-contracts.md`
6. `prompts.md`
7. `feature-list.md`
8. `test-cases.md`
9. `evolution-policy.md`
10. `session-playbook.md`
11. `decision-log.md`
12. `task-board.json`
13. `progress.md`
14. temporary conversation context

Interpretation:

- PRD defines product direction
- architecture doc defines the planned controlled-growth platform
- tech spec defines the current implementation shape
- schema defines explicit contracts
- API contracts define external boundaries
- prompts define model behavior boundaries
- feature list defines the product inventory and milestone plan
- test cases define executable acceptance for implemented features

## 2.1 Skill Guidance

When writing, reviewing, or refactoring code, apply `karpathy-guidelines` as the default behavioral lens:

- think before coding
- keep changes surgical
- prefer the simplest solution that solves the request
- state assumptions and tradeoffs explicitly
- define verifiable success criteria before declaring done

## 2.2 Planning vs Handoff

`task-board.json` and `progress.md` serve different purposes and must both be maintained.

Use `task-board.json` for:

- task ids
- dependency order
- current planned status
- deliverables
- acceptance checks

Use `progress.md` for:

- session-by-session handoff
- files changed in the session
- checks actually run
- blockers discovered during real work
- next recommended step

## 3. Non-Negotiable Boundaries

Must preserve:

- explicit user-triggered workflows
- evidence-backed outputs
- approval before high-risk external actions
- auditability for learning and reuse
- canonical docs as the source of truth

Must not drift into:

- automatic incident detection by default
- generic chatbot behavior
- autonomous code rewriting as a growth mechanism
- silent schema or prompt-boundary mutation
- unapproved external task or review publication
- multi-agent complexity without a concrete workflow need

## 4. Session Workflow

Each session must follow this order.

### Step 1: Initialize

- run `.\init.ps1`
- confirm required docs exist
- confirm the next task from `task-board.json`
- read the latest handoff in `progress.md`
- read the current growth and approval boundaries before implementation

### Step 2: Pick One Primary Task

Work on one primary task at a time unless the second change is a tiny same-task follow-up.

Allowed task types:

- incident workflow task
- growth-kernel task
- AI code review task
- doc alignment task

### Step 3: Implement Narrowly

During implementation:

- work only inside the chosen task boundary
- prefer explicit contracts over hidden behavior
- keep high-risk actions proposal-first
- keep growth features candidate-first
- preserve tenant isolation and auditability

### Step 4: Evaluate Independently

Do not declare success from inspection alone.

Before marking a task complete, collect evidence:

- what changed
- which acceptance checks ran
- what passed
- what remains risky

### Step 5: Handoff

At session end:

- update `task-board.json`
- append a new session record in `progress.md`
- record the next recommended task
- record blockers and assumptions

## 4.1 Controlled Growth

The growth system must obey:

`session evidence -> skill candidate -> approved reuse`

Default rule:

- evidence may be recorded automatically
- candidate skills may be proposed automatically
- active skills, canonical-doc changes, and behavior changes must not be silently promoted

## 5. Completion Gate

A task is `done` only when all are true:

1. the deliverable exists
2. the relevant acceptance checks were executed or concretely simulated with evidence
3. regression risk against existing workflows was considered
4. `progress.md` contains a factual handoff

## 6. Human Escalation Gates

Ask the human only when one of these happens:

- the feature list itself needs a product-level tradeoff decision
- a change would materially alter scope or product promises
- a new external dependency changes complexity enough to alter roadmap assumptions
- a broken intermediate state cannot be recovered safely from the local workspace

Do not ask for implementation details that can be decided from project files.

## 7. Current Defaults

Unless a later canonical file changes them, use these defaults:

- stack: Python 3.11 + FastAPI + Pydantic
- incident entry: Feishu manual trigger
- current evidence source: local controlled knowledge documents
- current output style: structured, source-aware, compact
- high-risk actions: approval required
- growth outputs: proposal-first and audit-backed

## 8. First Principle

This repository should evolve by accumulating approved reusable patterns.

It must not evolve by silently rewriting its own truth or expanding scope from one optimistic session.
