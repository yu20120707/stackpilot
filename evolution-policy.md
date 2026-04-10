# Evolution Policy

## 1. Purpose

This file defines how the project improves over time without letting the AI silently rewrite scope, contracts, or behavior.

The goal is controlled learning, not uncontrolled drift.

## 2. Core Rule

Use this promotion path:

`session evidence -> skill candidate -> approved canonical docs`

Interpretation:

- `session evidence`: what happened in one real session
- `skill candidate`: a reusable workflow the agent may apply again
- `approved canonical docs`: stable project truth after review

The agent may automatically record evidence.
The agent must not automatically promote evidence into high-authority docs without clear justification and, for high-risk changes, human approval.

## 3. Three Information Layers

### 3.1 Session Evidence

Store session-specific facts in `progress.md`.

Evidence includes:

- task id
- files changed
- checks run
- failure modes
- final working path
- blockers
- next recommended task

Evidence is allowed to be incomplete or temporary as long as it is factual.

### 3.2 Skill Candidate

A skill candidate is a reusable procedure, not a one-off story.

Promote evidence into a skill candidate only if all conditions are true:

- the workflow is non-trivial
- it can be reused across sessions
- it has clear trigger conditions
- it has clear inputs, steps, failure signals, and verification steps

Additional promotion gate:

- either the pattern has worked at least twice
- or it failed once in a meaningful way and a stable recovery path was found

Skill candidates should stay lightweight until reused again.

### 3.3 Canonical Docs

Canonical docs describe stable truth for this project.

Current canonical docs are:

- `rd-incident-ai-assistant-prd.md`
- `tech-spec.md`
- `schema.md`
- `api-contracts.md`
- `prompts.md`
- `feature-list.md`
- `test-cases.md`
- `agent.md`
- `evolution-policy.md`
- `session-playbook.md`
- `decision-log.md`
- `task-board.json`
- `progress.md`

## 4. What The Agent May Auto-Update

Safe automatic updates:

- append factual session evidence to `progress.md`
- update task status in `task-board.json`
- add low-risk clarifying notes inside implementation-facing docs when the current task explicitly requires it

Examples of low-risk clarifications:

- a missing fixture note in `test-cases.md`
- a missing file-path note in `tech-spec.md`
- a missing validation note in `feature-list.md`

These changes must stay inside the current approved scope.

## 5. What Requires Human Confirmation

The agent must ask before promoting any of the following into canonical docs:

- product scope changes in `rd-incident-ai-assistant-prd.md`
- user-visible behavior changes that alter trigger words, output shape, or confidence semantics
- contract changes in `schema.md`
- external integration boundary changes in `api-contracts.md`
- prompt behavior changes in `prompts.md`
- new external systems or dependencies that materially increase complexity
- anything that moves work from `P0` into `P1` or `P2`

The agent may prepare a proposed patch, but it should not silently treat these as routine cleanup.

## 6. Vibecoding Discipline

The project allows fast iteration, but only inside controlled boundaries.

Required behavior:

- one primary task per thread
- one stable acceptance target before implementation starts
- contracts before convenience
- fixtures before hand-wavy confidence
- evidence before marking `done`
- handoff before ending the session

Forbidden behavior:

- mixing two task ids in one implementation thread
- changing schema and renderer in passing without recording the contract change
- widening P0 scope because a tool or model makes it easy
- declaring success from inspection only when a check was expected

## 7. Change Impact Matrix

Use this matrix when changing files.

- If `schema.md` changes, review `tech-spec.md`, `api-contracts.md`, `prompts.md`, `feature-list.md`, `test-cases.md`, and any parser or renderer code.
- If `prompts.md` changes, review `schema.md`, `test-cases.md`, and all output rendering paths.
- If `api-contracts.md` changes, review `schema.md`, `tech-spec.md`, adapters, fixtures, and error-path tests.
- If `rd-incident-ai-assistant-prd.md` changes, review every implementation-facing doc and confirm whether task decomposition still holds.
- If `feature-list.md` changes, review `test-cases.md` and `task-board.json`.
- If `session-playbook.md` or `agent.md` changes, review `init.ps1` and `progress.md` expectations.

## 8. Decision Escalation

When the agent discovers a repeated ambiguity, it should not silently invent a permanent answer.

Instead:

1. record the evidence in `progress.md`
2. decide whether this is a skill candidate, a canonical-doc change, or a human decision
3. if it is a stable project-level choice, add or update an item in `decision-log.md`
4. if it changes scope or contracts, ask the human

## 9. Minimum Evidence For Reuse

Before telling future sessions to trust a pattern, the agent should have:

- a concrete example
- a failure or boundary condition
- a verification method
- a reason the pattern is expected to hold again

Without these four, keep the lesson as session evidence only.

## 10. First Principle

The agent should grow by accumulating verified working patterns.

It should not grow by silently rewriting the project around its own guesses.
