# VaultWares ADK — Functionalities

## Overview

**vaultwares-adk** is a reusable multi-agent coordination framework built on Redis pub/sub. It is designed as a Git submodule for VaultWares projects, providing personality-driven agents ("Extroverts"), centralized project management ("Lonely Manager"), and specialized task processing.

---

## Core Infrastructure

### 1. Redis Pub/Sub Coordination (`redis_coordinator.py`)
- **RedisCoordinator** class wraps the Redis client for all inter-agent communication.
- Channels: `tasks` (main coordination), `alerts` (critical alerts from LonelyManager).
- Methods: `publish()`, `listen()`, `stop()`, `set_state()`.
- All messages are JSON-encoded with `agent`, `action`, `task`, `target`, and `details` fields.

### 2. Agent Status Enum (`enums.py`)
- Four strict states: `WORKING`, `WAITING_FOR_INPUT`, `RELAXING`, `LOST`.
- No deviations — all agents must use exactly these values.

### 3. Hook Registry (`hook_registry.py`)
- Global lifecycle event system with `register(event, callback)` and `trigger(event, *args)`.
- Available hooks: `pre/post_agent_start`, `pre/post_agent_stop`, `pre/post_heartbeat`, `pre/post_communication`, `pre/post_status_update`, `pre/post_user_interaction`, `pre/post_assignment`, `pre/post_subagent_spawn`, `pre/post_subagent_remove`.
- Error-safe: hook failures are logged but don't block other hooks.

### 4. Agent Base (`agent_base.py`)
- **AgentBase** class provides heartbeat thread (every 5 seconds), status management, and Redis wiring.
- Methods: `start()`, `send_heartbeat()`, `update_status()`, `stop()`.

---

## Agent Classes

### 5. ExtrovertAgent (`extrovert_agent.py`) — 406 lines
The social personality base class. All specialized agents inherit from this.

**Core Behaviors:**
- **Heartbeat** — Every 5 seconds via background thread; 5 missed heartbeats = LOST alert from manager.
- **Status Broadcasting** — Every 60 seconds or after every 3 user actions; includes current task, status enum, and peer snapshot.
- **Socialization Routine** — On every user interaction: heartbeat → status broadcast → project re-evaluation → peer acknowledgement → team status report.
- **Peer Registry** — Local dictionary tracking all known agents with their status and last heartbeat timestamp.
- **Project Alignment** — Periodic re-reading of TODO.md and ROADMAP.md; notifies team of re-alignment.
- **GitHub Integration** — Optional `GitHubSkills` for creating PRs and dispatching tasks via `repository_dispatch`.

**Key Methods:**
- `start()` / `stop()` — Lifecycle with JOIN/LEAVE announcements.
- `on_user_interaction()` — Entry point before every response; triggers full socialization.
- `get_team_report()` — Formatted team status block for every response.
- `create_pr()` — Create GitHub PR via GitHubSkills.
- `dispatch_task_via_github()` — Trigger GitHub repository_dispatch for CI-based task routing.

### 6. LonelyManager (`lonely_manager.py`) — 489 lines
The project guardian and team coordinator.

**Core Responsibilities:**
- **Heartbeat Monitoring** — Checks every agent's heartbeat every 5 seconds; fires LOST alerts after 5 missed.
- **Status Update Requests** — Requests status from all agents every 60 seconds.
- **Project File Tracking** — Loads and monitors TODO.md and ROADMAP.md.
- **Team State Persistence** — Writes full team state to Redis hashes (`lonely_manager:team_state:<agent_id>`) with 5-minute TTL.
- **Alignment Enforcement** — Nudges agents silent for >2 minutes.
- **Alert Broadcasting** — Publishes critical alerts (LOST agents, missed heartbeats) to Redis `alerts` channel.
- **Task Assignment** — Dispatches tasks to specific agents via Redis + optional GitHub dispatch.

### 7. Manager Base (`manager_base.py`)
- **Manager** class for spawning and managing subagents asynchronously.
- Methods: `spawn_subagent()`, `remove_subagent()`, `listen_for_updates()`, `send_mass_message()`, `shutdown()`, `run()`.

### 8. SubAgent (`subagent.py`)
- Async task listener inheriting from AgentBase.
- `listen_for_tasks()` — Async generator listening on the agent's Redis channel.
- `SubAgent.run()` — Main loop that processes tasks via `handle_task()`.

---

## Specialized Agents

### 9. ImageAgent (`agents/image_agent.py`) — 152 lines
- Skills: image_generation, image_editing, masking, inpainting, outpainting, prompt_generation, workflow_creation, comfyui_export.
- 7 task handlers dispatched via `_perform_task()`.

### 10. TextAgent (`agents/text_agent.py`) — 140 lines
- Skills: text_generation, captioning, prompt_engineering, VQA, batch_VQA, prompt_enhancement, workflow_creation, comfyui_export.
- 6 task handlers.

### 11. VideoAgent (`agents/video_agent.py`) — 160 lines
- Skills: video_trimming, video_resizing, frame_sampling, per_frame_effects, video_captioning, video_analysis, workflow_creation, comfyui_export.
- 8 task handlers.

### 12. WorkflowAgent (`agents/workflow_agent.py`) — 167 lines
- Skills: workflow_parsing, step_mapping, comfyui_export, diffusion_export, workflow_validation, error_reporting.
- 6 task handlers; exports ComfyUI JSON with node structure.

---

## Skills System

### 13. GitHubSkills (`skills/github_skills.py`) — 227 lines
- `create_pr(branch, title, body, base, owner, repo)` — Creates GitHub PRs.
- `dispatch_task(target_agent, task, description, **extra)` — Triggers `repository_dispatch` events.
- Graceful degradation when `GITHUB_TOKEN` is unavailable.

### 14. Redis Communication Skill (`skills/redis_comm_skill.py`)
- Pure functions: `publish_status()`, `send_heartbeat()`, `broadcast_message()`, `register_peer()`, `update_peer_status()`, `handle_incoming_message()`.
- Routes HEARTBEAT, STATUS, STATUS_UPDATE, JOIN, LEAVE actions.

### 15. Spawn Agent Skill (`skills/spawn_agent_skill.py`)
- `spawn_subagent(manager, agent_class, *args, **kwargs)` — Async subagent spawning with unique IDs.
- `remove_subagent(manager, subagent_id)` — Task cancellation and cleanup.

### 16. Print Skill (`skills/print_skill.py`)
- Simple logging: `print_message(agent_id, task)`.

---

## Importlib Shim (`vaultwares_adk/__init__.py`)

- Dynamic module loader for Python import compatibility (hyphens in directory name).
- Respects dependency order: enums → redis_coordinator → agent_base → extrovert_agent → lonely_manager.
- Exports: `AgentStatus`, `RedisCoordinator`, `AgentBase`, `ExtrovertAgent`, `LonelyManager`, `GitHubSkills`.

---

## Communication Architecture

| Channel | Purpose |
|---------|---------|
| `tasks` | All coordination: heartbeats, status, JOIN/LEAVE, assignments, results |
| `alerts` | Critical alerts from LonelyManager (LOST agents, missed heartbeats) |

### Message Actions
| Action | Purpose |
|--------|---------|
| `HEARTBEAT` | Agent alive signal (every 5s) |
| `STATUS` / `STATUS_UPDATE` | Full status broadcast |
| `JOIN` | New agent announcement |
| `LEAVE` | Agent departure |
| `ASSIGN` | Manager assigns task to target agent |
| `TASK_COMPLETE` | Agent reports task done |
| `PROJECT_CHECK` | Re-evaluation of project files |
| `REQUEST_UPDATE` | Manager requests all agents report |
| `REALIGN` | Manager nudges silent/drifting agent |
| `ACK_PEERS` | Agent acknowledges peer statuses |
| `RESULT` | Agent publishes task result |
| `ALERT` | Critical alerts (missed heartbeats, LOST) |

---

## Configuration & Standards

### Project Guidelines
- **INSTRUCTIONS.md** — Enterprise-wide coding standards (TypeScript, Python, C#).
- **CONTRIBUTING.md** — Contribution workflow, security checklists, PR process.
- **STYLE.md** — UI/design guidelines (typography, colors, glassmorphism, dark/light mode).
- **skills.md** — Agent skill definitions including mandatory Extrovert behaviors.
- **extrovert_agent.md** — Extrovert personality philosophy and behavioral contract.

### Agent Personality Definitions (`definitions/`)
- `image_agent.md`, `text_agent.md`, `video_agent.md`, `workflow_agent.md`.
- Describe skills, task types, example usage, and integration instructions per agent.

### Threading Model
- **AgentBase**: `_heartbeat_thread` (daemon).
- **ExtrovertAgent**: Adds `_status_thread` (daemon).
- **LonelyManager**: Adds `_heartbeat_monitor_thread` + `_update_request_thread` (daemon).
- **SubAgent/Manager**: `asyncio` for async task handling.
- Daemon threads auto-terminate when main thread exits.

### Error Handling
- GitHubSkills degrades gracefully without tokens.
- Malformed JSON messages silently skipped.
- Hook errors caught and logged, don't block other hooks.
- LonelyManager publishes structured alerts with severity levels (HIGH, CRITICAL).

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `redis` | ≥5.0.0 | Redis Python client for pub/sub coordination |
