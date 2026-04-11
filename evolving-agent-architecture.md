# Evolving Agent Architecture

## 1. Goal

This document defines the next-step product architecture after the current incident-analysis baseline.

Target positioning:

`A controlled workflow agent for R&D teams that can analyze incidents, assist code review, and evolve through approved memory, skills, and feedback loops.`

It is not a generic multi-agent platform.
It is not a self-modifying codebase agent.

## 2. Design Principle

The repository now has two levels of truth:

1. `Current implemented foundation`
   Feishu-first incident analysis with citations, follow-up summaries, task drafts, and postmortem drafts.
2. `Planned controlled-growth platform`
   Shared memory, retrieval, approval, audit, and skill mechanisms reused by incident and code-review workflows.

The growth layer must obey:

`evidence -> candidate -> approval -> active reuse`

## 3. Shared Kernel

### 3.1 Memory Layer

Scope:

- `thread memory`
- `user memory`
- `org memory`

Usage:

- preserve workflow continuity
- store stable preferences
- remember approved patterns
- shape org-level review defaults and postmortem structure

Constraint:

- memory supports decisions
- memory does not rewrite canonical docs automatically

Runtime precedence for convention-shaped behavior:

- explicit request
- user preference memory
- org default memory
- safe fallback

### 3.2 Retrieval Layer

Scope:

- query planning
- source routing
- evidence ranking
- bounded second-pass retrieval

Usage:

- incident evidence lookup
- review policy lookup
- historical pattern reuse

Constraint:

- retrieval returns evidence and proposals
- retrieval does not silently turn weak hits into strong conclusions

### 3.3 Approval Policy

Scope:

- high-risk action gating
- behavior-change gating
- skill lifecycle gating

Required approval examples:

- external task sync
- external review comment publishing
- skill activation
- canonical-doc promotion

### 3.4 Interaction Recorder

Scope:

- trigger history
- output snapshots
- user corrections
- acceptance and rejection signals
- failure and retry evidence

Usage:

- audit
- evaluation
- skill mining input

### 3.5 Skill System

Lifecycle:

- `draft`
- `approved`
- `active`
- `retired`

Usage:

- store reusable workflow patterns
- route scenario-specific rules
- support team-specific behavior

Constraint:

- skills start as proposals
- skills never bypass approval

### 3.6 Audit And Rollback

Required properties:

- every growth action is attributable
- every active skill has version history
- every approval action is reviewable
- every promoted change can be rolled back

## 4. Workflow A: Incident Agent

Primary loop:

`trigger -> load thread -> retrieve evidence -> diagnose -> draft actions -> approve -> execute -> record outcome`

Core user-visible outputs:

- current assessment
- known facts
- impact scope
- next actions
- citations
- conclusion summary
- task draft
- postmortem draft

## 5. Workflow B: AI Code Review

Primary loop:

`submit diff/pr -> normalize review request -> retrieve policy/evidence -> generate findings -> approve -> publish -> record acceptance`

Current MVP note:

- the runtime entry remains Feishu-first
- a workflow router dispatches explicit review triggers to a dedicated review flow
- GitHub publication is draft-first and approval-gated
- review focus can come from explicit request text, stored preference memory, or tenant org defaults
- accepted findings are recorded explicitly before they can influence draft skill mining

Core user-visible outputs:

- overall review assessment
- structured findings
- evidence-backed comments
- uncertainty and missing context
- publish-or-draft decision

## 6. Non-Negotiable Safety Boundaries

The platform must not automatically:

- rewrite canonical product or contract docs
- expand scope based on one session
- execute high-risk external actions without approval
- modify business code as part of self-evolution
- publish review comments without confirmation
- share tenant-specific memory or skills across tenants

## 7. Phase Plan

### Phase 1: Controlled Learning

- thread memory
- interaction recorder
- audit trail
- draft-only skill candidates

### Phase 2: Approved Reuse

- skill registry
- approval-backed skill activation
- user and org preference memory
- retrieval routing improvements

### Phase 3: Controlled Action

- action proposal queue
- confirmation-backed task sync
- postmortem publish path
- review publish path

### Phase 4: Cross-Scenario Expansion

- AI code review workflow
- shared review policies
- review feedback reuse
- cross-workflow approved skill reuse

## 8. Module Direction

Expected new services over time:

- `app/services/kernel/memory_service.py`
- `app/services/kernel/org_convention_service.py`
- `app/services/kernel/action_queue_service.py`
- `app/services/kernel/audit_log_service.py`
- `app/services/kernel/interaction_recorder.py`
- `app/services/retrieval/planner.py`
- `app/services/retrieval/router.py`
- `app/services/retrieval/ranker.py`
- `app/services/incident_action_service.py`
- `app/services/skill_miner.py`
- `app/services/skill_registry.py`
- `app/services/approval_policy.py`
- `app/services/action_queue.py`
- `app/services/workflow_router.py`
- `app/services/review/flow.py`
- `app/services/review/diff_reader.py`
- `app/services/review/service.py`
- `app/services/review/publish_service.py`

## 9. Final Product Definition

The intended end state is:

`A Feishu-first and repo-aware workflow agent that can analyze incidents and review code, while evolving only through auditable evidence, approval-gated skills, and controlled external actions.`
