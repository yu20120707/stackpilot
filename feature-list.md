# Feature List

## 1. Purpose

This document defines the product-level feature inventory for the next version of `stackpilot`.

Current codebase reality:

- the implemented foundation is still `Feishu incident analysis`
- the implemented expansion now includes `controlled growth + action loop + AI code review + org convention shaping`

This file therefore serves two purposes:

1. preserve the already-proven incident foundation
2. define the next feature boundaries without drifting into an unsafe generic agent platform

## 2. Product Frame

Target product:

`An evolving workflow agent for R&D teams, centered on incident collaboration and AI-assisted code review.`

Shared rule:

- every high-risk action is proposal-first
- every reusable pattern is candidate-first
- every evolution step is auditable

## 3. Feature Groups

There are now four feature groups:

- `Foundation`: implemented incident-analysis baseline
- `Incident Workflow`: next incident-specific upgrades
- `Growth Kernel`: shared controlled-learning capabilities
- `AI Code Review`: second workflow built on the same kernel

## 4. Foundation Inventory

These capabilities already exist and remain the base layer.

| ID | Feature | Status | Purpose |
| --- | --- | --- | --- |
| FD-001 | Feishu manual trigger | Implemented | Start analysis from an explicit user command |
| FD-002 | Thread loading and normalization | Implemented | Build a stable request from discussion context |
| FD-003 | Deterministic local evidence retrieval | Implemented | Return source-aware evidence from controlled docs through planner, router, ranker, and bounded second-pass recall |
| FD-004 | Structured incident summary | Implemented | Produce current assessment, facts, impact, actions, and citations |
| FD-005 | Follow-up summary output | Implemented | Support rerun and summarize-thread flows |
| FD-006 | Todo draft generation | Implemented | Generate task suggestions from discussion state |
| FD-007 | Confirmation-gated task sync contract | Implemented | Keep external task execution under manual approval |
| FD-008 | Postmortem draft generation | Implemented | Produce reviewable post-incident draft output |
| FD-009 | Action proposal queue and approval loop | Implemented | Persist reviewable task/postmortem actions and execute them through explicit thread commands |
| FD-010 | Evidence ledger and draft skill candidates | Implemented | Record visible workflow evidence, audit skill lifecycle events, and mine draft reusable patterns without runtime auto-activation |

## 5. Incident Workflow Features

These are the incident-domain upgrades around the implemented baseline. Continuity, retrieval quality, the approval-backed action loop, the interaction recorder, and the first org-style shaping layer are now in place.

| ID | Feature | Status | Priority | Summary |
| --- | --- | --- | --- | --- |
| INC-001 | Explicit thread memory | Implemented | High | Replace marker-based follow-up inference with persisted thread state |
| INC-002 | User and org memory | Implemented | Medium | Store stable review preferences and tenant-scoped team conventions that shape defaults |
| INC-003 | Retrieval planning and routing | Implemented | High | Upgrade keyword retrieval into planner, router, and evidence ranking |
| INC-004 | Evidence quality threshold | Implemented | High | Prevent weak citations from being treated as sufficient proof |
| INC-005 | Action proposal queue | Implemented | High | Persist task and postmortem proposals before confirmation |
| INC-006 | Approval-backed action execution | Implemented | High | Confirm, execute, and write back external task results |
| INC-007 | Incident interaction recorder | Implemented | Medium | Record trigger, output, correction, approval, and adoption signals |
| INC-008 | Team-style postmortem output | Implemented | Medium | Let tenant-scoped team conventions shape draft structure and section labels |

### INC-001 Explicit Thread Memory

Goal:

- preserve same-thread continuity through explicit persisted state

User-visible outcome:

- follow-up requests become more stable and less sensitive to reply text shape

### INC-003 Retrieval Planning And Routing

Goal:

- turn retrieval into a source-aware evidence pipeline

User-visible outcome:

- incident replies cite more relevant runbooks, release notes, and policy sources

### INC-005 Action Proposal Queue

Goal:

- make action generation reviewable before execution

User-visible outcome:

- users first see a draft package, then decide whether to execute it

## 6. Growth Kernel Features

These features are shared by incident and code-review workflows.

| ID | Feature | Status | Priority | Summary |
| --- | --- | --- | --- | --- |
| GR-001 | Evidence ledger | Implemented | High | Record factual visible workflow outcomes, corrections, and acceptance signals |
| GR-002 | Memory layer | Implemented | High | Support thread, user, and org-level reusable context plus org convention shaping |
| GR-003 | Approval policy | Implemented | High | Centralize approval-backed action and skill lifecycle gates |
| GR-004 | Audit log and rollback | Implemented | High | Make every promotion and execution traceable and reversible |
| GR-005 | Skill candidate registry | Implemented | Medium | Store draft reusable workflow patterns |
| GR-006 | Skill approval lifecycle | Implemented | Medium | Promote skills through draft, approved, active, retired states |
| GR-007 | Evaluation and feedback loop | Planned | Medium | Score which behaviors helped, failed, or were corrected |
| GR-008 | Canonical knowledge gateway | Planned | High | Keep product truth anchored to approved docs, not chat memory |

### GR-001 Evidence Ledger

Goal:

- capture what actually happened in real runs

Included evidence:

- trigger
- output snapshot
- user correction
- approval action
- execution result
- adoption signal

### GR-005 Skill Candidate Registry

Goal:

- let the system suggest reusable skills without silently activating them

Constraint:

- first output is a candidate, not a rule

## 7. AI Code Review Features

This is the second workflow built on the shared kernel.

The `M5` MVP is now implemented for explicit Feishu-triggered review requests using inline patch or GitHub PR input, structured draft findings, safe degraded replies, and approval-backed GitHub draft publishing.
The first `M6` safe-reuse slice is also implemented: explicit review focus routing, repeated-request preference memory, explicit finding feedback recording, and draft review-focus skill candidates.
The `M7` org-memory slice is now also implemented: explicit user focus still wins, but org-level review defaults can shape review focus when user memory is absent.

| ID | Feature | Priority | Summary |
| --- | --- | --- | --- |
| CR-001 | Manual review trigger | High | Start review from explicit diff, patch, commit range, or PR input |
| CR-002 | Diff normalization | High | Convert raw patch data into a stable internal review request |
| CR-003 | Structured review findings | High | Output findings grouped by risk instead of free-form prose |
| CR-004 | Evidence-backed comments | High | Bind each finding to file, hunk, or policy evidence |
| CR-005 | Safe degraded review reply | High | Admit uncertainty when diff or context is incomplete |
| CR-006 | Review policy routing | Medium | Let teams choose review focus such as bug risk or test gaps |
| CR-007 | Draft-first publish flow | High | Preview findings before posting to an external review system |
| CR-008 | Adoption recording | Medium | Track which findings were accepted or ignored |
| CR-009 | Review preference memory | Medium | Learn stable review-output preferences per user or team |
| CR-010 | Review skill candidates | Low | Propose reusable review patterns from accepted findings |

### CR-001 Manual Review Trigger

Goal:

- preserve explicit user control over code review entry

Included inputs:

- `git diff`
- patch text
- commit range
- PR patch

### CR-003 Structured Review Findings

Goal:

- produce compact, defensible findings instead of generic review summaries

Expected output shape:

- overall assessment
- concrete findings
- risk level
- evidence reference
- missing context

### CR-007 Draft-First Publish Flow

Goal:

- separate analysis from publication

User-visible outcome:

- review output can stay as a draft or be explicitly published after approval

## 8. Milestone Plan

| Milestone | Focus | Primary Features |
| --- | --- | --- |
| M1 | Stabilize incident continuity | INC-001, GR-001, GR-002 |
| M2 | Improve evidence quality | INC-003, INC-004 |
| M3 | Close the incident action loop | INC-005, INC-006, GR-003, GR-004 |
| M4 | Activate controlled growth | GR-005, GR-006, GR-007, GR-008 |
| M5 | Launch AI code review MVP | CR-001, CR-002, CR-003, CR-004, CR-005, CR-007 |
| M6 | Grow review reuse safely | CR-006, CR-008, CR-009, CR-010 |
| M7 | Apply org conventions across workflows | INC-002, INC-007, INC-008, GR-002 |
| M8 | Anchor canonical team knowledge | GR-008 |

## 9. Explicit Non-Goals

These features are out of scope unless explicitly re-opened:

- autonomous full-repo review scanning
- automatic code fixing and commit submission
- automatic publication of external comments or tasks without confirmation
- self-rewriting canonical docs
- automatic schema or prompt-boundary mutation
- generic multi-agent orchestration as a product goal
- unbounded external dependency expansion
- cross-tenant sharing of memory or skills

## 10. Acceptance Rule

Any new feature should satisfy at least one of these outcomes:

- better incident continuity
- better evidence quality
- safer external action handling
- stronger auditability
- more reusable approved workflow knowledge
- more useful code review assistance

If a proposed feature does not improve one of the six outcomes above, it should not enter the roadmap.
