# Agent Working Contract

## 1. Purpose

This file defines the minimum harness for this project so future AI coding sessions do not drift.

Project target:

`Feishu-first incident discussion assistant for R&D teams`

P0 core chain:

`manual Feishu trigger -> current-thread context -> source citation lookup -> structured summary -> reply in the same thread`

This project is a focused AI product for one discussion workflow, not a multi-agent platform.

## 2. Canonical Sources

Every new session must treat itself as stateless and rebuild context from files, not memory.

Start by running `.\init.ps1`.

Then read in this order before doing any implementation:

1. `rd-incident-ai-assistant-prd.md`
2. `tech-spec.md`
3. `schema.md`
4. `api-contracts.md`
5. `prompts.md`
6. `feature-list.md`
7. `test-cases.md`
8. `evolution-policy.md`
9. `session-playbook.md`
10. `decision-log.md`
11. `task-board.json`
12. `progress.md`

If any of these files conflict, resolve them in this order of authority:

1. `rd-incident-ai-assistant-prd.md`
2. `tech-spec.md`
3. `schema.md`
4. `api-contracts.md`
5. `prompts.md`
6. `feature-list.md`
7. `test-cases.md`
8. `evolution-policy.md`
9. `session-playbook.md`
10. `decision-log.md`
11. `task-board.json`
12. `progress.md`
13. Temporary conversation context

PRD defines what to build.
Tech spec defines how P0 is organized.
Schema defines data contracts.
API contracts define external integration boundaries.
Prompts define model behavior boundaries.
Feature list defines the implementation surface.
Test cases define acceptance targets.
Evolution policy defines how project knowledge can be promoted without drift.
Session playbook defines when to open a new thread and how to start it safely.
Decision log defines which project choices are already closed and when they may be reopened.
Task board defines planned work status and dependencies.
Progress log defines what each session actually did and what the next session should know.

## 2.1 Planning vs Handoff

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

Do not use `progress.md` as a substitute for task status tracking.
Do not use `task-board.json` as a substitute for session handoff notes.

## 3. Non-Negotiable Boundaries

Must preserve:

- Single main scenario: manual analysis of one Feishu discussion thread
- Single P0 chain: trigger -> analyze -> cite -> summarize -> reply
- Product behavior: cite sources when possible, admit missing information when not
- Scope control: one-shot thread analysis first, richer follow-up later

Must not expand P0 into:

- automatic incident detection
- Jira or external task sync
- generic chatbot behavior
- multi-agent platform work
- meeting assistant or speech transcription work
- self-built model, vector store, or agent framework work
- heavy frontend work

If a requested change pushes the project outside these boundaries, stop and explicitly call out the scope break.

## 4. Session Workflow

Each implementation session must follow this order.

### Step 1: Initialize

- Run `.\init.ps1`
- Confirm required governance and spec files exist
- Confirm the current next task from `task-board.json`
- Read the latest handoff in `progress.md`
- Confirm the thread boundary rules from `session-playbook.md`

### Step 2: Pick One Task

Only pick one primary task at a time unless the second task is a tiny follow-up inside the same module.

Allowed:

- One scaffold task
- One Feishu integration task
- One knowledge task
- One reply rendering task

Not allowed:

- Scaffold + callback handling + reply rendering in one unbounded session
- P0 work mixed with P1 follow-up, todo draft, or external sync
- Reopening product scope while implementing a module

### Step 3: Implement Narrowly

During implementation:

- Work only inside the chosen task boundary
- Reuse current PRD decisions instead of reopening them
- Prefer the minimum code path that keeps P0 explainable
- Keep interfaces explicit and testable
- Keep user-visible behavior aligned with the product language in the PRD

### Step 4: Evaluate Independently

Do not declare success from code inspection alone.

Before marking a task complete, collect evidence:

- What changed
- Which acceptance checks ran
- What passed
- What remains risky

If no executable verification is available yet, record the exact reason and leave the task `in_progress` or `blocked`, not `done`.

### Step 5: Handoff

At session end:

- Update `task-board.json`
- Append a new session record in `progress.md`
- Record next recommended task
- Record blockers and assumptions

No session is complete until the handoff is written down.

## 4.1 Controlled Growth

The agent is allowed to accumulate verified working patterns, but it must do so in the order defined by `evolution-policy.md`.

Default rule:

- session evidence may be recorded automatically
- reusable patterns may be proposed as candidates
- high-authority docs and stable skills must not be silently rewritten from one session's intuition

When a repeated ambiguity appears, check `decision-log.md` before reopening the question.

## 5. Task Status Rules

Use only these statuses in `task-board.json`:

- `not_started`: no implementation work has begun
- `in_progress`: code or docs are actively being changed
- `blocked`: cannot continue due to a real dependency or missing decision
- `done`: acceptance checks passed and evidence is recorded in `progress.md`

Do not mark `done` based on:

- partial code skeleton
- TODO comments
- "core logic is basically there"
- model self-confidence

## 6. Completion Gate

A task can be marked `done` only when all of the following are true:

1. The deliverable exists.
2. The acceptance checks for that task have been executed or concretely simulated with evidence.
3. Regressions against the current P0 chain were considered.
4. `progress.md` contains a short factual handoff.

If any one of the four is missing, the task is not done.

## 7. Recovery And Rollback Discipline

When work goes wrong, do not keep piling changes onto a broken state.

Recovery order:

1. Stop adding scope.
2. Identify the last known-good task from `progress.md`.
3. Isolate whether the break is in callback parsing, thread loading, knowledge lookup, summary generation, or reply delivery.
4. Revert only the smallest local change set required.
5. Re-run the relevant acceptance checks.
6. Write down the failure mode in `progress.md`.

If a session leaves the workspace in an unverified state, the handoff must say so explicitly.

## 8. Human Escalation Gates

Ask the human before proceeding if any of these happens:

- The implementation would change the product scope in the PRD
- A new external dependency materially changes complexity
- The next task depends on an unresolved product decision
- A broken intermediate state cannot be safely recovered from local context

Do not ask the human for choices that can be resolved from existing project files.

## 9. Current Project Defaults

Unless later files explicitly change them, use these defaults:

- Implementation draft stack: Python 3.11 + FastAPI + Pydantic
- Entry: Feishu event callback with manual command trigger
- Knowledge source: local Markdown or text documents
- Output: structured summary plus source citations in the same Feishu thread
- No mandatory database in P0
- No Jira integration in P0

## 10. First Principle

This harness exists to make long-running AI implementation recoverable.

The agent is not judged by how much code it writes in one sitting.
The agent is judged by whether another fresh session can safely continue from the files it leaves behind.
