# DOCUMENTATION — oh-my-codex (OMX) Integration for VaultWares ADK

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [How It Works](#how-it-works)
4. [Platform Compatibility](#platform-compatibility)
5. [Communication Methods](#communication-methods)
6. [Team Orchestration](#team-orchestration)
7. [Skill Routing System](#skill-routing-system)
8. [Task Queue (Claim-Safe Lifecycle)](#task-queue-claim-safe-lifecycle)
9. [Mailbox System](#mailbox-system)
10. [Demo Guide](#demo-guide)
11. [IDE Integration](#ide-integration)
12. [Agent Prompts](#agent-prompts)
13. [OMX AGENTS.md Contract](#omx-agentsmd-contract)
14. [API Reference](#api-reference)
15. [FAQ](#faq)

---

## Overview

This integration brings the [oh-my-codex (OMX)](https://github.com/Yeachan-Heo/oh-my-codex) agentic team orchestration patterns into the VaultWares ADK multi-agent framework.

**What OMX provides:**
- A workflow layer for AI coding agents (originally for OpenAI Codex CLI)
- Team-based parallel execution with leader/worker coordination
- Skill-based keyword routing for activating workflows
- Claim-safe task lifecycle management
- Structured inter-agent messaging (mailbox system)
- Durable state management under `.omx/`

**What this integration adds:**
- Full OMX team orchestration built on top of VaultWares' existing Redis pub/sub infrastructure
- Leader/worker pattern that writes **real code files** to your project directory
- Git-integrated output — all generated code is committed directly to the current branch
- GitHub PR creation for human review of team output
- Platform-agnostic design (no tmux dependency for core features)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    OMX Team Orchestration                            │
│                                                                     │
│  ┌──────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐ │
│  │  OMX Leader   │  │  Worker 1  │  │  Worker 2  │  │  Worker N  │ │
│  │  (orchestrate)│  │  (execute) │  │  (execute) │  │  (execute) │ │
│  └──────┬───────┘  └──────┬─────┘  └──────┬─────┘  └──────┬─────┘ │
│         │                 │               │               │         │
│         └────────┬────────┴───────┬───────┴───────┬───────┘         │
│                  │                │               │                  │
│         ┌────────▼────────────────▼───────────────▼────────┐        │
│         │           Redis Pub/Sub (tasks channel)           │        │
│         │  + TaskQueue (Redis Hash)  + Mailbox (Redis Hash) │        │
│         └──────────────────────────────────────────────────┘        │
│                                                                     │
│  Pipeline: team-plan → team-prd → team-exec → team-verify          │
│                                                                     │
│  Output: Real files → Git commits → GitHub PR                       │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Map

| Component | File | Purpose |
|-----------|------|---------|
| `TeamOrchestrator` | `omx_integration/team_orchestrator.py` | High-level API for running a team session |
| `OMXLeader` | `omx_integration/omx_leader.py` | Orchestrates workers through the pipeline |
| `OMXWorker` | `omx_integration/omx_worker.py` | Executes assigned tasks, writes files |
| `TaskQueue` | `omx_integration/task_queue.py` | Claim-safe task lifecycle via Redis |
| `Mailbox` | `omx_integration/mailbox.py` | Structured inter-agent messaging |
| `SkillRouter` | `omx_integration/skill_router.py` | Keyword detection and skill activation |
| Demo runner | `omx_integration/demo/run_demo.py` | End-to-end demo that generates real code |

---

## How It Works

### The OMX Pipeline

The team follows the OMX canonical pipeline:

1. **team-plan** — The leader decomposes the work into bounded tasks with clear ownership.
2. **team-prd** — Tasks are created in the Redis-backed task queue with unique IDs.
3. **team-exec** — The leader assigns tasks to workers using claim-safe tokens. Workers execute their assigned slices, writing real files to the project directory.
4. **team-verify** — The leader checks that all tasks reached `completed` status.
5. **team-fix** (loop) — If verification fails, iterate.

### What "Real Code" Means

Unlike agents that run in isolated VMs, OMX workers write directly to your project directory:

1. Worker receives an ASSIGN message with task details and output file specifications.
2. Worker creates/writes the specified files on disk.
3. Worker runs `git add` + `git commit` with Lore Commit Protocol metadata.
4. Worker publishes TASK_COMPLETE on the Redis channel.
5. Files are **immediately accessible** in your working tree and Git history.

### AGENTS.md Operating Contract

The `AGENTS.md` file at the project root serves as the **top-level operating contract** for all agents. It defines:

- **Operating principles**: Solve directly, delegate only when it helps, verify before claiming.
- **Delegation rules**: When to use deep-interview, ralplan, team, ralph, or solo execution.
- **Child agent protocol**: Leader responsibilities vs worker responsibilities.
- **Keyword detection**: Automatic skill activation from user messages.
- **Verification protocol**: Size-appropriate verification for all changes.
- **Lore Commit Protocol**: Structured commit messages with decision records.

---

## Platform Compatibility

### Where Can It Run?

| Platform | Support Level | Notes |
|----------|--------------|-------|
| **macOS** | ✅ Full | Native Python + Redis. Optional tmux for OMX CLI team mode. |
| **Linux** | ✅ Full | Native Python + Redis. |
| **Windows Native** | ✅ Core features | Python + Redis for Windows. No tmux needed. |
| **Windows WSL** | ✅ Full | Behaves like Linux. Best Windows experience. |
| **GitHub Actions** | ✅ Full | Demo runs in CI. Redis available via service container. |

### Do I Need WSL?

**No.** The core OMX integration (team orchestration, task queue, mailbox, skill routing) works natively on Windows with Python and Redis for Windows. You only need WSL if you want:
- Full OMX CLI (`omx` command) with tmux-based team mode
- The `omx team` durable tmux session management

### Is It CLI Only or Can It Work Inside an IDE?

**Both.** The integration provides:

1. **CLI**: Run `python -m omx_integration.demo.run_demo` from any terminal.
2. **IDE (VS Code)**: Use the provided `.vscode/omx-launch.json` with launch configurations for:
   - Running the full team demo
   - Running individual tests
   - Running all tests
3. **Python API**: Import and use programmatically:
   ```python
   from omx_integration import TeamOrchestrator
   orchestrator = TeamOrchestrator(team_name="my-team", project_dir=".")
   orchestrator.setup()
   orchestrator.run_pipeline(tasks=[...])
   orchestrator.teardown()
   ```

### How Can I Communicate With My Agents?

There are three communication channels:

1. **Redis Pub/Sub** (real-time) — Agents publish and subscribe to the `tasks` channel for heartbeats, status updates, task assignments, and completion signals.
2. **Mailbox System** (structured, durable) — The leader sends structured messages to worker mailboxes stored in Redis hashes. Messages support notification/delivery tracking.
3. **GitHub PRs** (output delivery) — Workers commit their output to Git. The orchestrator creates a PR for human review. This is where you see and interact with the team's work.

---

## Team Orchestration

### TeamOrchestrator

The high-level interface for running a team session:

```python
from omx_integration import TeamOrchestrator

orchestrator = TeamOrchestrator(
    team_name="feature-auth",
    project_dir="/path/to/repo",
    worker_count=3,
    worker_roles=["executor", "executor", "executor"],
    redis_host="localhost",
    redis_port=6379,
)

# Setup: creates leader + workers, registers everyone
orchestrator.setup()

# Run pipeline: plan -> assign -> execute -> verify
report = orchestrator.run_pipeline(tasks=[
    {
        "subject": "Implement auth middleware",
        "description": "Add JWT verification middleware",
        "output_files": {
            "src/middleware/auth.py": "... file content ...",
        },
    },
    # ... more tasks
])

# Teardown: shutdown all agents, clean up Redis state
orchestrator.teardown()
```

### OMXLeader

The leader follows the AGENTS.md child_agent_protocol:

```python
from omx_integration import OMXLeader

leader = OMXLeader(team_name="my-team", project_dir=".")
leader.start()

# Plan
tasks = leader.create_plan([
    {"subject": "Task 1", "description": "..."},
    {"subject": "Task 2", "description": "..."},
])

# Assign
leader.assign_tasks([
    {"task_id": tasks[0].task_id, "worker_id": "worker-1"},
    {"task_id": tasks[1].task_id, "worker_id": "worker-2"},
])

# Verify
report = leader.verify_completion()
print(leader.get_team_report())

# Shutdown
leader.shutdown()
leader.cleanup()
```

### OMXWorker

Workers execute bounded subtasks:

```python
from omx_integration import OMXWorker

worker = OMXWorker(
    worker_id="worker-1",
    team_name="my-team",
    project_dir=".",
    role="executor",
)
worker.start()

# Execute task — writes files and commits to Git
created_files = worker.execute_task(
    task_id="task-001",
    subject="Implement utility module",
    description="Create helper functions",
    output_files={"src/utils.py": "... content ..."},
)

worker.stop()
```

---

## Skill Routing System

The SkillRouter implements the AGENTS.md keyword_detection contract:

```python
from omx_integration import SkillRouter

router = SkillRouter(omx_runtime=False)

# Explicit invocation
result = router.route('$plan "implement the auth module"')
# → {"skill": "plan", "task": "implement the auth module", "blocked": False}

# Keyword detection (case-insensitive)
result = router.route("Let's plan the authentication module")
# → {"skill": "plan", "task": "...", "blocked": False}

# Runtime-only skills are gated
result = router.route("$team 3:executor fix tests")
# → {"skill": "team", "blocked": True, "reason": "$team requires OMX CLI/runtime."}

# List all skills
skills = router.list_skills()
```

### Supported Skills

| Skill | Keywords | Runtime Only | Description |
|-------|----------|:---:|-------------|
| `deep-interview` | interview, deep interview, don't assume, ouroboros | No | Socratic deep interview |
| `ralplan` | ralplan, consensus plan | No | Consensus planning |
| `ralph` | ralph, don't stop, keep going | Yes | Persistent completion loop |
| `autopilot` | autopilot, build me | Yes | Full autonomous pipeline |
| `ultrawork` | ultrawork, ulw, parallel | Yes | Parallel agents |
| `team` | team, swarm | Yes | Team orchestration |
| `plan` | plan this, let's plan | No | Planning workflow |
| `analyze` | analyze, investigate | No | Root-cause analysis |
| `cancel` | cancel, stop, abort | No | Cancel active modes |
| `tdd` | tdd, test first | No | Test-first development |
| `build-fix` | fix build, type errors | No | Fix build errors |
| `code-review` | code review | No | Code review |
| `security-review` | security review | No | Security audit |
| `web-clone` | web-clone, clone site | No | Website cloning |

---

## Task Queue (Claim-Safe Lifecycle)

The TaskQueue implements the OMX team-api task lifecycle with version-checked claims:

```
create_task(subject) → claim_task(task_id, worker, version) → transition_status(completed)
```

### Task States

```
PENDING → IN_PROGRESS → COMPLETED
                      → FAILED
                      → CANCELLED
```

### Claim Safety

Claims use version checking to prevent race conditions:
1. `create_task()` creates a task with version=1.
2. `claim_task()` checks `expected_version` matches current — fails if another agent already claimed.
3. `transition_status()` checks `claim_token` matches — only the holder can transition.

---

## Mailbox System

Structured message passing between team members:

```python
from omx_integration import Mailbox

mailbox = Mailbox(team_name="my-team")

# Send message
msg = mailbox.send_message("leader", "worker-1", "Start task X")

# Broadcast
mailbox.broadcast("leader", ["worker-1", "worker-2"], "Sync checkpoint")

# List messages
messages = mailbox.list_messages("worker-1")

# Delivery tracking
mailbox.mark_notified("worker-1", msg.message_id)
mailbox.mark_delivered("worker-1", msg.message_id)
```

---

## Demo Guide

### Running the Demo

```bash
# From the project root:
python -m omx_integration.demo.run_demo
```

The demo:
1. Creates a team with 1 leader + 3 executor workers.
2. Worker 1 creates a utility module (`omx_integration/utils/`).
3. Worker 2 creates a test suite (`omx_integration/tests/`).
4. Worker 3 creates agent prompts and VS Code configuration.
5. Each worker commits its output to Git.
6. The leader verifies all tasks completed.

### Demo Output

The demo produces these **real files** in the project:

| Worker | Files Created |
|--------|--------------|
| worker-1 | `omx_integration/utils/team_utils.py`, `omx_integration/utils/__init__.py` |
| worker-2 | `omx_integration/tests/test_skill_router.py`, `omx_integration/tests/test_task_queue.py` |
| worker-3 | `omx_integration/prompts/executor.md`, `omx_integration/prompts/architect.md`, `omx_integration/prompts/verifier.md`, `.vscode/omx-launch.json` |

### Running Tests

```bash
python -m unittest discover omx_integration/tests/ -v
```

### Fallback Mode

If Redis is not available, the demo automatically falls back to a file-only mode that writes all files directly without team orchestration.

---

## IDE Integration

### VS Code

A launch configuration is provided at `.vscode/omx-launch.json`:

1. **OMX Demo: Run Team** — Runs the full team orchestration demo.
2. **OMX Demo: Skill Router Test** — Runs skill router tests.
3. **OMX Demo: All Tests** — Runs the complete test suite.

To use: Open the Run & Debug panel (Ctrl+Shift+D), select a configuration, and press F5.

### PyCharm

Create a Python run configuration with:
- Module: `omx_integration.demo.run_demo`
- Working directory: project root
- Environment: `PYTHONPATH=.`

### Any Terminal

```bash
cd /path/to/vaultwares-adk
python -m omx_integration.demo.run_demo
```

---

## Agent Prompts

The integration includes OMX-style agent prompt files under `omx_integration/prompts/`:

| Prompt | Role | Key Behaviors |
|--------|------|---------------|
| `executor.md` | Implementation | Write code, stay in scope, commit with Lore protocol |
| `architect.md` | Analysis | Read-only analysis, tradeoffs, risk assessment |
| `verifier.md` | Validation | Run tests, lint, check completeness |

These follow the AGENTS.md agent_catalog specification.

---

## OMX AGENTS.md Contract

The `AGENTS.md` file at the project root defines the operating contract for all agents. Key sections:

### Operating Principles
- Solve directly when safe; delegate only when it materially helps.
- Prefer evidence over assumption; verify before claiming completion.
- Use the lightest path that preserves quality.

### Delegation Rules
- `$deep-interview` → unclear intent, missing boundaries.
- `$ralplan` → requirements clear, plan/tradeoffs need review.
- `$team` → approved plan needs parallel execution.
- `$ralph` → persistent completion loop with one owner.
- **Solo execute** → task is scoped, one agent can finish it.

### Child Agent Protocol
**Leader**: Pick mode, delegate bounded tasks, own verification.
**Worker**: Execute assigned slice, stay in scope, report blockers.

### Verification
Size-appropriate verification:
- Small changes → lightweight check.
- Standard changes → standard verification.
- Large/security → thorough verification.

### Lore Commit Protocol
Structured commit messages with:
- Intent line (why, not what).
- Trailers: `Constraint:`, `Rejected:`, `Confidence:`, `Scope-risk:`, `Directive:`, `Tested:`, `Not-tested:`.

---

## API Reference

### TeamOrchestrator

| Method | Description |
|--------|-------------|
| `__init__(team_name, project_dir, worker_count, ...)` | Create orchestrator |
| `setup()` | Start leader and workers |
| `run_pipeline(tasks)` | Execute full plan→assign→execute→verify pipeline |
| `teardown()` | Shutdown team and clean up |

### OMXLeader

| Method | Description |
|--------|-------------|
| `start()` | Start leader with heartbeat |
| `register_worker(worker_id, role)` | Add worker to team |
| `create_plan(task_descriptions)` | Decompose work into tasks |
| `assign_tasks(assignments)` | Assign tasks to workers with claim tokens |
| `record_completion(task_id, claim_token)` | Mark task completed |
| `verify_completion()` | Check all tasks are done |
| `get_team_report()` | Generate formatted status report |
| `shutdown()` | Shut down team |
| `cleanup()` | Clean up Redis state |

### OMXWorker

| Method | Description |
|--------|-------------|
| `start()` | Start worker with heartbeat |
| `execute_task(task_id, subject, description, output_files)` | Write files and commit |
| `stop()` | Stop worker |

### TaskQueue

| Method | Description |
|--------|-------------|
| `create_task(subject, description, owner)` | Create PENDING task |
| `claim_task(task_id, worker, expected_version)` | Claim with version check |
| `transition_status(task_id, from, to, claim_token)` | Move task to new state |
| `list_tasks()` | List all tasks |
| `get_task(task_id)` | Get specific task |
| `cleanup()` | Remove all team tasks |

### Mailbox

| Method | Description |
|--------|-------------|
| `send_message(from, to, body)` | Send message |
| `broadcast(from, workers, body)` | Broadcast to multiple |
| `list_messages(worker)` | List worker's messages |
| `mark_notified(worker, message_id)` | Mark as seen |
| `mark_delivered(worker, message_id)` | Mark as acted upon |
| `cleanup(workers)` | Remove all mailbox data |

### SkillRouter

| Method | Description |
|--------|-------------|
| `route(message)` | Route message to matching skill |
| `list_skills()` | List all skill definitions |
| `register_handler(skill_name, handler)` | Register skill handler |

---

## FAQ

### Q: Do subagents write real code I can access?
**A:** Yes. Workers write files directly to the project directory and commit them to Git. The files are immediately visible in your working tree.

### Q: Will my code be stuck in an invisible Linux VM?
**A:** No. The OMX integration writes to whatever directory you specify as `project_dir`. In the demo, this is the repository root. Files persist in your Git history.

### Q: Does it work on Windows without WSL?
**A:** Yes, for the core features (team orchestration, task queue, mailbox, skill routing). You need Python 3.10+ and Redis for Windows. The full OMX CLI (`omx` command with tmux) requires macOS/Linux or WSL.

### Q: Can I use this from VS Code?
**A:** Yes. Launch configurations are provided in `.vscode/omx-launch.json`. You can also import and use the Python API directly in any script.

### Q: How do workers communicate?
**A:** Three channels: (1) Redis pub/sub for real-time messages, (2) Mailbox system for structured durable messages, (3) Git commits for persisted output.

### Q: What happens if Redis is not available?
**A:** The demo has a fallback mode that writes files directly without team coordination. The core file generation still works.

### Q: Can I customize the worker roles?
**A:** Yes. Pass `worker_roles=["executor", "architect", "verifier"]` to `TeamOrchestrator`.

### Q: How does the Lore Commit Protocol work?
**A:** Every commit includes structured metadata: intent line, worker ID, team name, task ID, confidence level, scope risk, and test coverage declarations.

### Q: What is the AGENTS.md file?
**A:** It's the top-level operating contract for all agents in the workspace — defining operating principles, delegation rules, skill routing, verification protocols, and more. It follows the oh-my-codex template format.
