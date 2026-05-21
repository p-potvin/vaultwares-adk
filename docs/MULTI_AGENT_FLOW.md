# VaultWares Multi-Agent Flow Protocol

> **Canonical reference.** All assistants operating a multi-agent run must follow
> this document exactly. Narrower execution surfaces (omx_integration prompts,
> agent definitions) must not contradict it.
>
> Related specs:
>
> - `docs/TASKS_MD_SCHEMA.md` — machine-parseable TASKS.md format
> - `docs/AGENT_TELEMETRY.md` — ledger fields, thought logs, pattern data
> - `docs/JULES_INTEGRATION.md` — Jules API reference and dispatch rules

---

## Trigger Phrases

Any of the following phrases in a user message activates the multi-agent flow:

| Phrase                   | Variant accepted                                 |
| ------------------------ | ------------------------------------------------ |
| "le stéphane bellavance" | "stéphane bellavance", "the stéphane bellavance" |
| "le réal t.v."           | "réal tv", "the réal t.v."                       |
| "le méchant changement"  | "méchant changement", "the méchant changement"   |

All three trigger the same flow. The phrases are interchangeable and exist for
cultural color. Do not assign different behavior to different phrases.

**Keyword detection is case-insensitive.**

---

## Verbosity Contract

> [!IMPORTANT]
> **Every agent — manager or worker — must be maximally verbose at every step.**
>
> Silence is a bug. If an agent is doing something, it says so. If it finished
> something, it reports exactly what it did and what it found. If it is waiting,
> it says why and for what. If something went wrong, it reports the full error
> with context.
>
> This applies to:
>
> - The manager narrating each phase transition
> - Workers announcing task start, progress milestones, and completion
> - Verification agents writing detailed, exhaustive findings (not summaries)
> - The final report including everything, not just highlights
>
> Agents must publish progress updates to Redis during long tasks, not only at
> completion. A reasonable cadence is every significant milestone or every
> 2 minutes, whichever comes first.

---

## Phase 1 — Interview and TASKS.md

### 1.1 Socratic Interview

**Always run the interview, even if the user provided extensive details.**
The interview exists to surface hidden assumptions, unspecified constraints, and
scope boundaries that the user did not think to mention.

The interviewing agent must:

1. Acknowledge the trigger phrase explicitly and state that a Socratic interview
   is beginning before asking the first question.
2. Ask one focused question at a time. Do not present lists of questions.
3. After each user answer, briefly restate your current understanding of that
   dimension before asking the next question.
4. Cover at minimum: goal and success definition, affected files/modules (identifying existing code to preserve), explicit out-of-scope areas, known constraints, security/privacy implications, expected test coverage (mandatory visual tests for GUIs), and preferred parallelism ceiling.
5. When confidence is high enough to write an unambiguous TASKS.md, declare
   the interview complete, summarize the full scope in one paragraph, and ask
   for confirmation before proceeding.

**Never interpret an affirmative answer during the interview as plan approval.**
"Yes", "correct", "exactly", "that's right" during the interview confirm an
answer, not the plan. If there is genuine ambiguity about whether the user
intends to approve the plan or confirm an interview answer, ask explicitly:
"Do you want me to proceed with writing the TASKS.md, or were you confirming
my last question?"

### 1.2 Maintenance of Hygiene Files

**TASKS.md must always include tasks for updating `TODO.md` and `ROADMAP.md`.**

- `TODO.md` should reflect the active task backlog for the current project state.
- `ROADMAP.md` should define the long-term vision and phase-based milestones.
- Old or stale entries must be cleared or archived to prevent noise.
- This is mandatory for every run.

### 1.3 Writing TASKS.md

After the interview, write `TASKS.md` at the workspace root (or relevant project
root if the task is scoped to a specific repo). Follow the schema in
`docs/TASKS_MD_SCHEMA.md` exactly.

Before writing, narrate:

- What you understood from the interview
- How many tasks you identified, how many are parallel, how many are blocking
- Which tasks you are assigning `CLOUD`, `ASYNC`, or `LOCAL` and why

After writing, print the full TASKS.md content for the user to review.

### 1.3 Plan Approval

The plan is approved when the user's message contains an explicit approval
signal in the current prompt. Accepted signals:

**Explicit keywords (always approve):**

- "commit", "go", "proceed", "approved", "approve", "deploy", "execute",
  "start", "launch", "let's go", "j'approuve", "go for it"

**High-confidence affirmations (approve with a confirmation step first):**

- "yes", "ok", "sure", "looks good", "seems fine", "that works"
- Before activating Phase 2, respond: "I'll take that as approval to begin
  Phase 2. Starting Redis and initializing the team now." — and pause for
  one second to allow a cancel.

**Never treat silence or a question as approval.**

---

## Phase 2 — Manager Initialization

### 2.1 Redis Startup

Before instantiating any agents:

1. Attempt to connect to Redis at `localhost:6379`.
2. If the connection fails, start Redis using the bundled config:
   `redis-server vaultwares-adk/redis.conf`
3. Retry the connection. If it still fails, **abort and tell the user clearly**
   with the exact error. Do not proceed without Redis.
4. Announce: "Redis is running. Starting team initialization."

### 2.2 Agent Instantiation

Instantiate between 1 and 4 `ExtrovertAgent` workers based on the number of
tasks marked `PARALLEL` in the first dispatch batch. Never exceed 4.

For each agent, announce:

- Agent ID (e.g., `worker-1`)
- Assigned role (executor, planner, debugger, verifier, architect)
- Role justification (one sentence)

**Role → personality mapping:**

```markdown
| OMX Role    | Use when                                  | System prompt source                   |
| ----------- | ----------------------------------------- | -------------------------------------- |
| `executor`  | Implementation, refactoring, writing code | `omx_integration/prompts/executor.md`  |
| `planner`   | Sub-planning, dependency analysis         | `omx_integration/prompts/planner.md`   |
| `debugger`  | Root cause analysis, error tracing        | `omx_integration/prompts/debugger.md`  |
| `architect` | Read-only analysis, tradeoffs (no writes) | `omx_integration/prompts/architect.md` |
| `verifier`  | Phase 4 verification, testing             | `omx_integration/prompts/verifier.md`  |
```

All workers inherit `ExtrovertAgent`. **Workers must use the provided Redis-based coordination infrastructure.** Using native subagent tools as "black boxes" is forbidden. All workers must follow the socialization routine (heartbeat, status, peer acknowledgement) on every user-facing response.

### 2.3 Subagent Independence

**Every subagent is responsible for its own agent ledger entry.** The manager
must not write ledger entries on behalf of workers. This ensures that the
ledger accurately reflects who did the work and the specific model used.

### 2.3 Redis Monitor Link

After team initialization, provide the RedisInsight link:

```
http://localhost:8011
```

If RedisInsight is not running, tell the user. Do not silently omit the link.

---

## Phase 3 — Execution Rounds

### 3.1 Dispatch

Each dispatch round:

1. Read TASKS.md and identify all tasks with status `[ ]` (FREE) whose
   blocking dependencies are all `[x]` (DONE).
2. Among eligible tasks, select those marked `PARALLEL` up to the worker count.
3. Assign one task per worker. Workers not receiving a task enter `RELAXING`.
4. **Announce every dispatch decision verbosely:**
    - Which tasks were dispatched, to which workers
    - Which tasks are still blocked and why (name the blocking dependency)
    - Which workers are RELAXING this round

### 3.2 Worker Behavior

Each worker, upon receiving a task:

1. Immediately publish status `WORKING` to Redis and update TASKS.md to `[~]`.
2. Announce task start: task ID, title, declared FILE_SCOPE, and planned
   approach in 2–3 sentences.
3. Publish progress updates during the task (every significant milestone or
   every 2 minutes).
4. On completion:
    - Write the agent ledger entry (see `docs/AGENT_TELEMETRY.md`).
    - Write the thought log entry (see `docs/AGENT_TELEMETRY.md`).
    - Update TASKS.md to `[x]`.
    - Publish `TASK_COMPLETE` to Redis with a full completion summary including
      files changed, decisions made, and anything the manager or other workers
      should know.
    - Set status to `WAITING_FOR_INPUT`.
5. **Step 4 must be inside a try/finally block.** Ledger and thought log are
   written whether the task succeeded or failed.

### 3.3 Dispatch Barrier

**The next dispatch round begins only when every active worker is in
`WAITING_FOR_INPUT` or `RELAXING`.**

The manager monitors Redis team state. When the quorum is reached:

1. Announce: "All workers are WAITING or RELAXING. Beginning next dispatch
   round." List the current status of each worker.
2. Check dependency graph against completed tasks.
3. Proceed to 3.1.

### 3.4 Dead Agent Protocol

If a worker misses 5 consecutive heartbeats (marked `LOST` by LonelyManager):

1. The manager announces the lost agent immediately with the last known status.
2. If the lost agent's task is critical-path: **pause the run and notify the
   user.** The user decides: reassign, restart, or abort.
3. If the lost agent's task is non-blocking: reassign to a RELAXING worker if
   one exists, otherwise pause and notify.
4. Never silently skip a lost agent's task.

### 3.5 Scope Contract

Workers must not:

- Modify files outside their declared `FILE_SCOPE`
- Spawn sub-agents or delegate to other workers
- Widen their task definition without manager approval
- Modify TASKS.md entries other than their own

If a worker discovers that their task requires touching out-of-scope files,
they publish a `BLOCKED` message with the reason and wait. The manager decides.

---

## Phase 4 — Verification Pass

When all execution tasks are `[x]` DONE, the manager transitions to
verification.

### 4.1 Agent Personality Change

Workers' system prompts are swapped to verification roles. They retain their
short-term context of the work just completed (passed as context by the
manager). The manager collects all `TASK_COMPLETE` summaries and injects them
as context into each verification agent's prompt.

**Do not clear the team state.** Reuse existing workers with new roles.

### 4.2 Verification Agents

Exactly three verification agents are dispatched (can overlap with existing
workers):

| Agent            | Output file                               | Scope                               |
| ---------------- | ----------------------------------------- | ----------------------------------- |
| Security agent   | `FINDINGS_SECURITY.md` at workspace root  | Files touched during execution only |
| Optimizer agent  | `FINDINGS_OPTIMIZER.md` at workspace root | Files touched during execution only |
| Brand ambassador | `FINDINGS_BRAND.md` at workspace root     | Files touched during execution only |

**Scope is bounded to files that were actually modified during Phase 3.**
Do not scan the full codebase — the context window cannot handle it and it
produces noise. The `files_modified` field from each agent ledger entry
provides the authoritative list.

**Verification agents must not modify code.** Read-only. Any finding must be
documented in their output file, not patched inline.

### 4.3 Findings Format

Each `FINDINGS_*.md` must be exhaustive, not summarized. Include:

- Severity (CRITICAL / HIGH / MEDIUM / LOW / INFO) for each finding
- Exact file path and line number where applicable
- Description of the issue
- Recommended remediation (for the manager's report — agents do not fix)

Agents must write their findings verbosely. "No issues found" must be
accompanied by a checklist of what was actually checked.

Agents must write their findings verbosely. "No issues found" must be
accompanied by a checklist of what was actually checked.

---

## Phase 5 — Testing and Visual QA

### 5.1 Test Dispatch

After all verification agents report `WAITING`, the manager dispatches test
tasks. Test tasks may overlap with Phase 3 workers.

### 5.2 Mandatory Visual Tests (GUI)

**Any task involving a GUI (direct or indirect) MUST include visual tests.**

- Use Playwright `toHaveScreenshot()` for visual regression detection.
- A baseline must be established on the first successful run.
- Subsequent runs must diff against the baseline.
- For **Web Extensions**, use Playwright with Firefox as the primary test target
  (see `docs/WEB_EXTENSION_TESTING.md` for the canonical flow).

### 5.3 Test Loop

Each test task follows a fixed loop: **write test → run test → fix if failing
→ repeat up to 3 times → stop.**

The retry count is tracked in Redis state (not just in the agent's local loop)
so the manager can see it. Field: `test_retry_count` in the team state hash.

### 5.2 Pass Criteria

A test run is considered passing when all newly written tests pass. The manager
must define the pass criteria in the TASKS.md test tasks before dispatching.
If no criteria are specified, the test agent must ask before running.

### 5.3 Concurrent Manager Work

While test agents are running, the manager:

1. Reads all three `FINDINGS_*.md` files.
2. Classifies each finding by severity.
3. Drafts the final report structure (work done, security issues, open bugs,
   brand inconsistencies — test results to be filled in after).
4. Waits for all test agents to reach `WAITING`.

---

## Phase 6 — Final Report and PR

### 6.1 Report

The manager presents the final report to the user. The report must include:

- **Work completed** — every task from TASKS.md with completion status
- **Security findings** — from `FINDINGS_SECURITY.md`, classified by severity
- **Optimization findings** — from `FINDINGS_OPTIMIZER.md`
- **Brand findings** — from `FINDINGS_BRAND.md`
- **Test results** — pass/fail, retry counts, any remaining failing tests
- **Open items** — anything that could not be completed and why
- **Thought log summary** — notable reasoning patterns observed across agents
  (for future routing optimization)

The report must be complete. Nothing is omitted because it reflects poorly on
the run. Bad news goes in the report.

### 6.2 Pull Request

After presenting the report, the manager opens a GitHub PR **regardless of
project state.** A failing test is not a reason to withhold the PR — the
reviewer (the user) decides what to merge.

PR contents:

- Title: "feat: [run ID] — [brief description from TASKS.md goal]"
- Body: the full final report, markdown-formatted
- Assign the user as reviewer if the GitHub username is available

The manager routine ends when the PR is confirmed open. Dismiss all workers
(they publish `LEAVE` to Redis and stop heartbeating).

### 6.3 Ledger — Final Manager Entry

Before dismissing the team, the manager writes one final agent ledger entry:

- `Kind: handoff`
- Summary includes: run ID, total tasks, pass rate, open findings count,
  PR URL

---

## Cross-Cutting Rules

### Ledger on Every Status Transition

Every agent (worker or manager) must write an agent ledger entry **before**
changing status to `WAITING_FOR_INPUT` or `RELAXING`. This is mandatory, not
optional.

Implementation pattern:

```python
try:
    # do the work
    ledger_kind = "code-change"
    ledger_summary = "..."
except Exception as e:
    ledger_kind = "general"
    ledger_summary = f"Task failed: {e}"
    raise
finally:
    write_ledger(kind=ledger_kind, summary=ledger_summary)
    write_thought_log(thoughts)
    update_status(WAITING_FOR_INPUT)
```

The ledger write happens whether the task succeeded or failed. A failed ledger
write must not suppress the original exception.

### Compact Before Team Init

The managing assistant must compact its conversation context immediately before
entering Phase 2. This prevents context window exhaustion during the multi-round
execution loop. After compaction, the manager reconstructs team state by:

1. Reading TASKS.md (ground truth for task state)
2. Listening to Redis for two full heartbeat cycles (10 seconds) to rebuild
   the peer registry

### Context Reconstruction

If the manager loses its context mid-run (crash, restart, context flush):

1. Read TASKS.md to identify where the run is.
2. Subscribe to the `tasks` Redis channel and listen for 10 seconds.
3. Read Redis hashes `lonely_manager:team_state:*` for current worker statuses.
4. Announce to the team: "Manager reconnected. Reconstructing state."
5. Resume from the current dispatch barrier.
