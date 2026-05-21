# TASKS.md Schema

Machine-parseable format for multi-agent task planning. Every TASKS.md written
during Phase 1 of the multi-agent flow must follow this schema exactly.
`assign_tasks.py` parses this format — deviations cause silent skip errors.

---

## Annotated Example

```markdown
# TASKS.md
<!-- run_id: vw-2026-05-12-001 -->
<!-- goal: Implement JWT authentication for the API -->
<!-- approved_by: p-potvin -->
<!-- approved_at: 2026-05-12T07:00:00-04:00 -->

## H1 [ ] Update TODO.md and ROADMAP.md
<!-- TASK_TYPE: LOCAL -->
<!-- FILE_SCOPE: TODO.md, ROADMAP.md -->
<!-- ESTIMATE: 5min -->

## 1 [ ] Set up JWT middleware
<!-- TASK_TYPE: CLOUD -->
<!-- FILE_SCOPE: src/middleware/auth.ts, src/types/jwt.ts -->
<!-- PARALLEL: 2 -->
<!-- BLOCKS: 3, 4 -->
<!-- ESTIMATE: 45min -->
Implement JWT verification middleware. Validate signature on every protected
route. Return 401 with structured JSON error on failure.

### 1a [ ] Write JWT types
<!-- TASK_TYPE: CLOUD -->
<!-- FILE_SCOPE: src/types/jwt.ts -->
<!-- PARALLEL: 1b -->

### 1b [ ] Write middleware function
<!-- TASK_TYPE: CLOUD -->
<!-- FILE_SCOPE: src/middleware/auth.ts -->
<!-- PARALLEL: 1a -->
<!-- BLOCKS: 1c, 1t -->

### 1c [ ] Write unit tests for middleware
<!-- TASK_TYPE: LOCAL -->
<!-- FILE_SCOPE: src/middleware/auth.test.ts -->
<!-- BLOCKS_ON: 1b -->

### 1t [ ] Visual tests for auth UI (if applicable)
<!-- TASK_TYPE: LOCAL -->
<!-- FILE_SCOPE: tests/e2e/auth.spec.ts -->
<!-- BLOCKS_ON: 1b -->
<!-- NOTE: Mandatory for GUI tasks. Use Playwright toHaveScreenshot(). -->

## 2 [ ] Add refresh token endpoint
<!-- TASK_TYPE: CLOUD -->
<!-- FILE_SCOPE: src/routes/auth.ts, src/services/token.ts -->
<!-- PARALLEL: 1 -->
<!-- BLOCKS: 3 -->
<!-- ESTIMATE: 60min -->

## 3 [ ] Integration tests
<!-- TASK_TYPE: LOCAL -->
<!-- FILE_SCOPE: tests/auth.integration.test.ts -->
<!-- BLOCKS_ON: 1, 2 -->
<!-- ESTIMATE: 30min -->

## 4 [ ] Update OpenAPI spec
<!-- TASK_TYPE: ASYNC -->
<!-- FILE_SCOPE: docs/openapi.yaml -->
<!-- BLOCKS_ON: 1, 2 -->
<!-- ESTIMATE: 20min -->
<!-- ASYNC_PROMPT: Update OpenAPI spec to document the JWT auth endpoints added in tasks 1 and 2. See FILE_SCOPE for relevant files. -->
```

---

## Field Reference

### File-level headers (HTML comments)

| Field | Required | Description |
|-------|----------|-------------|
| `run_id` | Yes | Unique identifier for this run. Format: `vw-YYYY-MM-DD-NNN` |
| `goal` | Yes | One-sentence description of the run's objective |
| `approved_by` | Yes | GitHub username of the approver |
| `approved_at` | Yes | ISO 8601 timestamp of approval |

### Task line format

```
## {ID} [{STATUS}] {Title}
```

- `ID` — integer for main tasks (`1`, `2`, `3`), alphanumeric for subtasks
  (`1a`, `1b`, `2a`)
- `STATUS` — one character:
  - ` ` (space) — FREE, not started
  - `~` — WORKING, in progress
  - `x` — DONE, completed

### Per-task HTML comments

All comments are parsed by `assign_tasks.py`. Order within the comment block
does not matter. All values are case-sensitive.

| Field | Required | Values | Description |
|-------|----------|--------|-------------|
| `TASK_TYPE` | Yes | `CLOUD` / `ASYNC` / `LOCAL` | Execution tier |
| `FILE_SCOPE` | Yes | Comma-separated file paths | Files this task is allowed to modify |
| `PARALLEL` | Conditional | Comma-separated task IDs | Tasks that can run concurrently with this one |
| `BLOCKS` | Conditional | Comma-separated task IDs | Tasks that cannot start until this one is `[x]` |
| `BLOCKS_ON` | Conditional | Comma-separated task IDs | Tasks that must be `[x]` before this one can start |
| `ESTIMATE` | Recommended | `{N}min` or `{N}h` | Time estimate for manager planning |
| `ASYNC_PROMPT` | Required for `ASYNC` tasks | String | The prompt sent to Jules API when dispatching |

> [!NOTE]
> `BLOCKS` and `BLOCKS_ON` are inverses. Use whichever reads more naturally
> for the task you are writing, but be consistent within a file.

---

## TASK_TYPE Values

| Value | Execution | On Redis? | Output |
|-------|-----------|-----------|--------|
| `CLOUD` | Cloud LLM agent (GitHub Copilot GPT-4 initially) | Yes | Direct code changes |
| `ASYNC` | Jules API (async, branch-per-task) | No | PR on its own branch |
| `LOCAL` | Ollama local model (via REST API) | No | PR on its own branch |

---

## FILE_SCOPE Overlap Rule

**No two `PARALLEL` tasks may have overlapping `FILE_SCOPE` entries.**

The planning agent must verify this before writing TASKS.md. If two tasks
need to touch the same file, one must `BLOCKS` the other, or they must be
combined into one task.

The manager must re-verify this before dispatching each round. A dispatch
that would violate FILE_SCOPE isolation must not proceed.

---

## Status Transition Rules

| From | To | Who | When |
|------|----|-----|------|
| ` ` (FREE) | `~` (WORKING) | Worker | Immediately on task receipt |
| `~` (WORKING) | `x` (DONE) | Worker | After ledger + thought log written |
| `~` (WORKING) | ` ` (FREE) | Manager | If worker goes LOST and task is reassigned |

No other transitions are valid.

---

## Writing Rules for Planning Agents

1. Write every task with the narrowest possible scope. If a task can be split
   into independently completable subtasks, split it.
2. Subtasks of a parent task inherit the parent's `FILE_SCOPE` constraint
   unless explicitly overridden.
3. **Mandatory Visual Tests**: Any task linked to a GUI must have a corresponding
   `...t` subtask for Playwright visual QA (`toHaveScreenshot`).
4. **Hygiene Tasks**: Always include a task (usually `H1`) to update `TODO.md`
   and `ROADMAP.md` at the start or end of the run.
5. Assign `TASK_TYPE` based on these heuristics:
   - **CLOUD**: Anything requiring reasoning, architecture decisions, or writing
     new code from scratch.
   - **ASYNC**: Jules API - Non-blocking, file-based, can tolerate latency (deep scans,
     documentation updates, test fixes, bug fixes from the findings reports).
   - **LOCAL**: Ollama - Mechanical, repetitive, deterministic: running tests, applying
     linting fixes, branding passes, refactoring with clear rules.
6. Every ASYNC task must have an `ASYNC_PROMPT` field with a self-contained
   prompt for Jules. Jules has no context from the Redis run — the prompt must
   include everything Jules needs.
7. Narrate your task decomposition decisions in the TASKS.md prose body (the
   lines after the comment block). Do not leave task bodies empty.
