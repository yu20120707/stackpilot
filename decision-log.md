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

### DEC-006

- Date: 2026-04-11
- Status: confirmed
- Decision: the project scope expands from an incident-only assistant into a controlled workflow agent with two first-class workflows: `incident` and `AI code review`.
- Why: both workflows share the same real backend problems: explicit state, evidence quality, approval gating, audit, and reusable team patterns.
- Alternatives considered:
  - keep the product incident-only
  - reframe the repository as a generic multi-agent platform
- Impacted files:
  - `rd-incident-ai-assistant-prd.md`
  - `evolving-agent-architecture.md`
  - `feature-list.md`
  - `README.md`
  - `agent.md`
- Revisit when:
  - the second workflow materially slows delivery of the shared kernel

### DEC-007

- Date: 2026-04-11
- Status: confirmed
- Decision: self-evolution may affect memory, skill candidates, reuse policy, and proposal generation, but it may not directly rewrite canonical docs, mutate contracts silently, or auto-modify product source code.
- Why: the project needs a credible "growth" story without creating an unsafe or non-explainable system.
- Alternatives considered:
  - autonomous self-modification of main product logic
  - no growth capabilities beyond session notes
- Impacted files:
  - `rd-incident-ai-assistant-prd.md`
  - `evolving-agent-architecture.md`
  - `feature-list.md`
  - `agent.md`
  - `README.md`
- Revisit when:
  - there is a mature approval, rollback, and evaluation system strong enough to justify broader automation

### DEC-008

- Date: 2026-04-11
- Status: confirmed
- Decision: the first growth-kernel implementation may auto-record evidence and auto-create `draft` skill candidates, but it must not auto-activate or runtime-apply those skills.
- Why: the project needs a credible self-evolution path, but runtime reuse without approval would make the behavior hard to explain and easy to destabilize.
- Alternatives considered:
  - immediately let mined skills influence incident routing
  - postpone all skill persistence until a later milestone
- Impacted files:
  - `evolving-agent-architecture.md`
  - `feature-list.md`
  - `tech-spec.md`
  - `task-board.json`
  - `progress.md`
- Revisit when:
  - there is a stronger approval UX and enough evidence that approved skills should start steering runtime behavior

### DEC-009

- Date: 2026-04-11
- Status: confirmed
- Decision: AI code review enters through the same Feishu callback surface as incident analysis, but review generation and GitHub publication stay in a separate review flow behind a workflow router and approval-gated publish action.
- Why: this keeps the external trigger model simple for users while preventing incident-specific orchestration and review-specific publishing logic from collapsing into one service.
- Alternatives considered:
  - extend the incident live flow directly with all review responsibilities
  - create a separate HTTP entrypoint for code review
- Impacted files:
  - `app/api/feishu.py`
  - `app/main.py`
  - `app/services/workflow_router.py`
  - `app/services/review/flow.py`
  - `tech-spec.md`
  - `progress.md`
- Revisit when:
  - a third workflow appears and the current router shape is no longer the cleanest separation boundary

### DEC-010

- Date: 2026-04-11
- Status: confirmed
- Decision: review preference memory and review skill mining may only learn from explicit user requests or explicit finding-feedback commands; they must not infer adoption from silence or automatically promote findings into active review rules.
- Why: review output is easy to overfit if the system treats missing response as approval, so the safe baseline is to require explicit focus requests or explicit `accepted/ignored` feedback before reusing patterns.
- Alternatives considered:
  - infer preference from every generated review without user confirmation
  - infer adoption from GitHub comment existence alone
- Impacted files:
  - `app/services/review/preference_service.py`
  - `app/services/review/flow.py`
  - `app/services/skill_miner.py`
  - `feature-list.md`
  - `progress.md`
- Revisit when:
  - GitHub-side resolution or code-change outcome signals are integrated strongly enough to support more reliable adoption measurement

### DEC-011

- Date: 2026-04-11
- Status: superseded
- Decision: runtime convention resolution must follow `explicit request -> user preference memory -> org defaults -> safe fallback`, and org memory may shape draft structure but may not silently replace canonical team policy.
- Why: this was the first safe org-memory shaping rule before approved canonical convention docs entered runtime precedence.
- Alternatives considered:
  - let org defaults override explicit user requests
  - keep org memory purely passive until a later milestone
- Impacted files:
  - `app/services/kernel/org_convention_service.py`
  - `app/services/review/preference_service.py`
  - `app/services/postmortem_service.py`
  - `app/services/postmortem_renderer.py`
  - `app/services/incident_action_service.py`
  - `feature-list.md`
  - `tech-spec.md`
- Revisit when:
  - `DEC-012` is implemented and stable enough to replace the old precedence note everywhere

### DEC-012

- Date: 2026-04-11
- Status: confirmed
- Decision: approved canonical convention docs live under the knowledge layer and override mutable org memory at runtime, while explicit user requests and remembered user preferences still remain higher-priority than canonical defaults for review focus.
- Why: approved convention docs need to be tenant-scoped, auditable, and reusable by both incident retrieval and review policy lookup without turning mutable org memory into the only source of truth.
- Alternatives considered:
  - keep canonical truth in `org.json`
  - add a knowledge-only gateway without letting approved docs influence runtime defaults
- Impacted files:
  - `app/services/kernel/canonical_convention_service.py`
  - `app/services/kernel/org_convention_service.py`
  - `app/services/knowledge_base.py`
  - `app/services/review/policy_service.py`
  - `app/services/incident_action_service.py`
  - `app/models/contracts.py`
  - `feature-list.md`
  - `tech-spec.md`
- Revisit when:
  - there is an approval-backed promotion flow that can create and version canonical convention docs directly from runtime evidence or approved skill candidates

### DEC-013

- Date: 2026-04-11
- Status: confirmed
- Decision: canonical convention promotion must reuse the existing pending-action approval loop and write versioned docs from a snapshot prepared at proposal time.
- Why: promotion is a high-risk behavior change, so it should be explicit, reviewable, auditable, and stable even if the underlying skill candidate changes before approval.
- Alternatives considered:
  - allow direct promotion without a pending action
  - rebuild the canonical document from the current skill candidate only at approval time
- Impacted files:
  - `app/services/convention_promotion_service.py`
  - `app/services/feishu_live_flow.py`
  - `app/services/kernel/canonical_convention_service.py`
  - `app/models/contracts.py`
  - `tech-spec.md`
  - `progress.md`
- Revisit when:
  - promotion evolves from one-shot versioned writes into a richer rollback or diff-review flow

### DEC-014

- Date: 2026-04-12
- Status: confirmed
- Decision: GitHub-side review outcomes enter the system only through durable publish anchors plus an explicit same-thread sync command; repo-side signals may enrich review outcome state and growth evidence, but they may not infer acceptance from silence or bypass the existing approval boundary for publication.
- Why: the project needs better adoption quality than Feishu-only feedback, but automatic polling, webhook ingestion, or code-change heuristics would expand system scope and make acceptance inference too loose for the current stage.
- Alternatives considered:
  - infer accepted findings from PR merge or later code changes
  - poll GitHub automatically after every publish
  - keep review reuse tied only to Feishu feedback forever
- Impacted files:
  - `app/clients/github_review_client.py`
  - `app/services/review/outcome_service.py`
  - `app/services/review/flow.py`
  - `app/models/contracts.py`
  - `feature-list.md`
  - `task-board.json`
  - `progress.md`
- Revisit when:
  - the repository gains a stronger GitHub-side signal source such as review-thread resolution, richer reply parsing, or an approval-safe webhook ingestion path

### DEC-015

- Date: 2026-04-12
- Status: confirmed
- Decision: service layout should separate domain-specific orchestration into `app/services/incident/` and `app/services/growth/`, while keeping `kernel`, `review`, and `retrieval` as dedicated shared or workflow packages.
- Why: the repository now has enough incident, growth, and review surface area that leaving most orchestration files flat under `app/services/` makes responsibilities harder to explain and maintain.
- Alternatives considered:
  - keep all non-review services flat under `app/services/`
  - add compatibility shims instead of moving files into real subpackages
- Impacted files:
  - `app/main.py`
  - `app/services/incident/*`
  - `app/services/growth/*`
  - `app/services/workflow_router.py`
  - `README.md`
  - `tech-spec.md`
  - `progress.md`
- Revisit when:
  - another workflow appears and the current package split no longer matches the real service boundaries
