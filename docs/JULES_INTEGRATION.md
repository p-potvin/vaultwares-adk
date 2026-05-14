# Jules Integration

Jules API reference and dispatch rules for the VaultWares multi-agent flow.
Jules handles `TASK_TYPE: ASYNC` tasks — non-blocking work that runs on its
own branch and delivers a PR, completely outside the Redis network.

**API Reference:** https://developers.google.com/jules/api/reference/rest

---

## API Surface (v1alpha)

**Base URL:** `https://jules.googleapis.com`

### Sessions

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/v1alpha/sessions` | Create a new Jules session (dispatch a task) |
| `GET` | `/v1alpha/{name=sessions/*}` | Get session status |
| `GET` | `/v1alpha/sessions` | List all sessions |
| `POST` | `/v1alpha/{session=sessions/*}:approvePlan` | Approve Jules' plan (body must be empty) |
| `POST` | `/v1alpha/{session=sessions/*}:sendMessage` | Send a follow-up message to a session |

### Sessions — Activities

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/v1alpha/{name=sessions/*/activities/*}` | Get a specific activity |
| `GET` | `/v1alpha/{parent=sessions/*}/activities` | List activities for a session |

### Sources

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/v1alpha/{name=sources/**}` | Get a source |
| `GET` | `/v1alpha/sources` | List sources (connected repos) |

---

## Dispatch Protocol

When the manager dispatches an `ASYNC` task:

1. **Create a Jules session** via `POST /v1alpha/sessions` with:
   - The repo as the source
   - The task's `ASYNC_PROMPT` field as the prompt
   - Request plan-before-execute mode

2. **Announce to the user:** "Dispatching task `{task_id}` to Jules. Session
   ID: `{session_id}`. Jules will plan and wait for approval."

3. **Poll session status** (`GET /v1alpha/{name=sessions/*}`) periodically
   (every 30 seconds is sufficient — Jules is async, not real-time).

4. **Approve the plan** when Jules returns it via `POST :approvePlan` with an
   empty body. Before approving, show the plan to the user and wait for their
   confirmation.

5. **Jules executes** on its own branch. The manager continues with the rest
   of the Redis team's dispatch rounds — Jules runs in the background.

6. **On completion:** Jules opens a PR. The manager records the PR URL in the
   telemetry and includes it in the final report.

---

## File Scope Constraint

> [!IMPORTANT]
> Jules tasks must have **zero `FILE_SCOPE` overlap** with any other concurrently
> running task — CLOUD, ASYNC, or LOCAL.
>
> Jules operates on a branch and cannot see real-time changes from the Redis
> team's workers. Overlap causes merge conflicts that no one is monitoring.
>
> The manager must verify this before dispatching any ASYNC task. If overlap
> exists, the Jules task must be deferred until the conflicting task is `[x]`.

---

## Branch Naming Convention

Jules creates its own branch. To keep things organized, the `ASYNC_PROMPT`
should instruct Jules to name the branch:

```
jules/{run_id}/{task_id}
```

Example: `jules/vw-2026-05-12-001/4`

---

## ASYNC_PROMPT Requirements

Jules has no context from the Redis run. Every ASYNC task's `ASYNC_PROMPT`
must be fully self-contained:

- What the task is (specific, unambiguous)
- Which files to modify (`FILE_SCOPE`)
- Any constraints or conventions to follow (link to AGENTS.md or relevant docs)
- What the expected output looks like
- Branch naming instruction (see above)

A vague prompt produces vague output. Treat the ASYNC_PROMPT as a standalone
task description for an agent with no prior context.

---

## Jules vs. Redis Team

| Dimension | CLOUD (Redis) | ASYNC (Jules) |
|-----------|---------------|---------------|
| On Redis network | Yes | No |
| Blocking | Yes — holds dispatch barrier | No — runs in background |
| Speed | Real-time | Minutes to hours |
| Context | Shares run context via manager | Fully isolated — prompt only |
| Output | Direct code changes | PR on its own branch |
| Plan approval | Not applicable | Required before execution |
| Cost | Cloud LLM tokens | Jules credits |

Jules is best for: deep codebase scans, documentation updates, test fixes,
non-urgent bug fixes, anything that can run asynchronously without blocking
the critical path.
