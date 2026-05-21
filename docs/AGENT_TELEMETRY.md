# Agent Telemetry

Structured logging for multi-agent runs. Every agent writes two artifacts on each status transition:

1. **Agent ledger entry** — structured event in `agent-ledger`
2. **Thought log** — raw reasoning output per run

Both written in the same `try/finally` block as the status transition.

## Worker Responsibility

**Every subagent is responsible for its own agent ledger entry and thought log.**
The managing assistant MUST NOT write ledger entries or thought logs on behalf
of workers. This ensures that:
1. The `actor` field accurately reflects the specific model used (which may 
   differ from the manager).
2. The `duration_seconds` is accurate to the sub-execution.
3. The raw thoughts are captured directly from the worker.

---

## Agent Ledger — Additional Fields

Base schema in `agent-ledger/AGENTS.md`. Multi-agent runs add:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `run_id` | string | Yes | From TASKS.md header (`vw-YYYY-MM-DD-NNN`) |
| `task_id` | string | Yes | TASKS.md task ID (e.g. `1b`) |
| `task_type` | enum | Yes | `CLOUD` / `ASYNC` / `LOCAL` |
| `phase` | enum | Yes | `execution` / `verification` / `testing` / `planning` / `management` |
| `duration_seconds` | integer | Yes | Wall time in seconds |
| `files_modified` | string[] | Yes | Actual files touched (may differ from `FILE_SCOPE`) |
| `complexity_score` | integer | Yes | 1–5 self-assessed. 1 = trivial, 5 = deeply complex |
| `outcome` | enum | Yes | `success` / `partial` / `failed` |
| `retry_count` | integer | Test tasks only | write→run→fix iterations used |
| `blocked_by` | string[] | Conditional | Task IDs blocking this task at start |
| `offload_candidate` | boolean | Yes | Could LOCAL or ASYNC have handled this? |
| `offload_reason` | string | If candidate | One sentence (e.g. "purely mechanical, no reasoning required") |
| `scope_violations` | string[] | If any | Files touched outside `FILE_SCOPE` with reason |

### Complexity Score

| Score | Meaning |
|-------|---------|
| 1 | Trivial — mechanical, no decisions |
| 2 | Simple — clear path, minimal reasoning |
| 3 | Moderate — tradeoffs evaluated, standard patterns |
| 4 | Complex — multiple approaches considered |
| 5 | Very complex — high uncertainty, deep domain knowledge |

---

## Thought Log

Captures raw reasoning — chain-of-thought, deliberation, self-correction.

### File Naming

```
THOUGHTS_{agent_id}_{run_id}.md
```

Location: workspace root. Example: `THOUGHTS_worker-1_vw-2026-05-12-001.md`

### Format

```markdown
# Thought Log — worker-1 — vw-2026-05-12-001

## Task 1b — 2026-05-12T07:45:00-04:00

**Status at entry:** WORKING
**Task:** Write JWT verification middleware

[Full reasoning output — do not summarize or filter. Include wrong turns,
reconsidered approaches, uncertainty. Value is in raw signal.]

**Outcome:** success
**Complexity assessed:** 3
**Offload candidate:** no — required reasoning about security edge cases

---
```

Include **everything**: rejected approaches, uncertainty, self-corrections,
questions the agent wished it could ask. Do not edit for readability.

### Pattern Detection Trailer

Append to each entry as YAML:

```yaml
pattern_data:
  task_type_accuracy: true          # Was TASK_TYPE assignment correct in hindsight?
  suggested_type: CLOUD             # What would you assign if redoing it?
  model_tier_fit: adequate          # underpowered | adequate | overkill
  estimated_token_cost: medium      # low | medium | high | very_high
  parallelizable_with_others: true
  reusable_pattern: false
  pattern_description: ""
```

---

## Manager Telemetry

Manager writes ledger entries at:
1. Phase transitions
2. Each dispatch round (tasks dispatched, workers assigned)
3. Dead agent events (LOST worker + decision)
4. Final handoff (run summary, PR URL)

---

## Retention

All telemetry files are committed to the project repo as part of the PR:
- `TASKS.md` (final statuses)
- `THOUGHTS_{agent_id}_{run_id}.md` (one per worker + manager)
- `FINDINGS_SECURITY.md`, `FINDINGS_OPTIMIZER.md`, `FINDINGS_BRAND.md`

Agent ledger entries go to `agent-ledger` repo only (not the project repo).
