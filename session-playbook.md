# Session Playbook

## 1. Purpose

This file defines when to start a new thread and how to operate once a new thread begins.

Every thread must behave like a stateless working session.

## 2. One Thread, One Primary Task

Default rule:

- one thread serves one primary task id from `task-board.json`

Examples:

- `ARC-001` gets its own thread
- `FEI-001` gets its own thread
- `SUM-001` gets its own thread

Small same-task fixes may stay in the same thread if they do not introduce a second task boundary.

## 3. Start A New Thread When

Open a new thread if any of these is true:

- the primary task id changes
- the current thread starts drifting into a second module or second deliverable set
- the current task is now handoff-ready as `done`, `blocked`, or clearly-described `in_progress`
- the next step needs a human decision on scope, dependencies, or product behavior
- the current workspace is left in an unverified intermediate state and work must pause
- the conversation has accumulated too much unrelated discussion and the next task would benefit from a clean, file-based restart

## 4. Do Not Start A New Thread For

Keep the same thread for:

- a tiny same-task import fix
- a missing config file inside the same task
- a narrow test or fixture addition that clearly belongs to the same task

If you need to explain why the second change still belongs to the same task, it is probably still safe.
If you need to justify a second deliverable set, start a new thread.

## 5. New Thread Startup Sequence

Follow this order.

1. Declare the session stateless.
2. Run `.\init.ps1`.
3. Read the required docs in the order defined by `agent.md`.
4. Read `task-board.json` and choose one primary task.
5. Read the latest handoff entry in `progress.md`.
6. State the session boundary before implementation:
   - primary task
   - not doing
   - files likely to change
   - acceptance checks to run
7. Implement only inside that boundary.
8. Before closing the thread, update `task-board.json` and `progress.md`.

## 6. Suggested Opening Prompt

Use this at the start of a new thread:

```text
This is a new stateless session. Rebuild context from workspace files only, not from prior chat memory.
Run .\init.ps1 first.
Then read the required docs in agent.md order and report only:
1. current next task
2. this thread's one primary task
3. what is explicitly out of scope
4. which files are likely to change
5. which acceptance checks will be used
Do not expand scope unless the files require escalation.
```

## 7. Suggested Closing Prompt

Use this before ending the thread:

```text
Before ending this session, decide whether the task is not_started / in_progress / blocked / done.
Do not mark done without evidence.
Then update:
1. task-board.json
2. progress.md
3. checks run
4. blockers
5. next recommended task
```

## 8. Thread Exit Standard

Do not end a thread until all are true:

- current task status is explicit
- evidence exists for any claimed progress
- blockers are written down
- next recommended task is written down
- a fresh session could continue from files alone

## 9. Special Note For This Repository

At the time this playbook was written, `.\init.ps1` reports `Git repo: no`.

That means thread discipline matters more than usual:

- shorter threads
- tighter task boundaries
- stronger handoff notes

Until version control is fully in use for implementation work, assume every new thread may need to recover from files only.
