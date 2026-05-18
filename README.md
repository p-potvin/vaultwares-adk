# vaultwares-adk

Reusable base for multi-agent coordination and communication using Redis.
Designed to be installed as a Git submodule into other VaultWares projects.

## Repository Layout

```
vaultwares-adk/
├── docs/                       # Reference docs (canonical)
├── vaultwares_adk/    # Python import shim (underscore — importable)
│   └── __init__.py             # importlib shim; loads core modules from submodule root
├── agents/                     # Specialized agent implementations
│   ├── __init__.py
│   ├── image_agent.py          # ImageAgent  — image generation & manipulation
│   ├── text_agent.py           # TextAgent   — text generation, captioning, VQA
│   ├── video_agent.py          # VideoAgent  — video trimming, frame sampling, effects
│   └── workflow_agent.py       # WorkflowAgent — ComfyUI/Diffusion workflow export
├── definitions/                # Agent personality & skill definition files
│   ├── agent_image.md
│   ├── agent_text.md
│   ├── agent_video.md
│   └── agent_workflow.md
├── .github/workflows/
│   ├── task_dispatch.yml       # Dispatches tasks to agents via repository_dispatch
│   └── pr_on_completion.yml    # Opens a PR when an agent reports task completion
├── enums.py                    # AgentStatus enum
├── redis_coordinator.py        # Low-level Redis pub/sub wrapper
├── agent_base.py               # AgentBase — heartbeat, status, coordinator wiring
├── extrovert_agent.py          # ExtrovertAgent — social base class, peer registry
├── lonely_manager.py           # LonelyManager — project guardian, alert engine
├── extrovert_agent.md          # Extrovert personality definition
├── skills.md                   # All agent skills and Extrovert rules
├── redis.conf                  # Redis server configuration
└── requirements.txt            # Python dependencies (redis>=5.0.0)
```

## Docs

Canonical reference docs live under `docs/`. Root-level `*.md` files that used to contain large documents are kept as thin pointers for compatibility with external tooling and links.

## Workspace Tools

- `tools/audit_agent_surfaces.py` — scans repos for agent-related instruction/skill/tool surfaces
- `tools/migrate_agent_assets.py` — cautious importer for reusable assets into this repo (dry-run by default)
- `tools/sync_adk_rules.py` — managed-block sync into consumer repos (`--check` / `--write`)

Consumer integration notes: `docs/consumer-integration.md`

## Getting Started

### 1. Add the submodule

```bash
git submodule add https://github.com/p-potvin/vaultwares-adk vaultwares-adk
git submodule update --init
```

### 2. Install Dependencies

```bash
pip install -r vaultwares-adk/requirements.txt
```

### 3. Start Redis

```bash
redis-server vaultwares-adk/redis.conf
```

### 4. Import in Python

Because Python cannot import from a package name that contains a hyphen, add
the **submodule root** to `sys.path` and import via the `vaultwares_adk`
package (with an underscore), which is the importlib shim bundled inside the
submodule:

```python
import sys, os
sys.path.insert(0, os.path.abspath("vaultwares-adk"))

from vaultwares_adk import ExtrovertAgent, LonelyManager, AgentStatus
from agents.image_agent import ImageAgent
from agents.text_agent import TextAgent
from agents.video_agent import VideoAgent
from agents.workflow_agent import WorkflowAgent
```

> The shim at `vaultwares_adk/__init__.py` uses `importlib` to load
> `enums.py`, `redis_coordinator.py`, `agent_base.py`, `extrovert_agent.py`,
> and `lonely_manager.py` from the submodule root and registers them under the
> `vaultwares_adk.*` namespace. No source files need to be modified.

## Classes

### `ExtrovertAgent`
The social backbone of any multi-agent team. Inherits from `AgentBase`.

- Sends a heartbeat to Redis every **5 seconds**
- Broadcasts a full status update every **60 seconds** and after every **3 actions**
- Maintains a live peer registry of all agents on the network
- Performs the **Socialization Routine** on every user interaction:
  1. Send heartbeat
  2. Broadcast status update
  3. Trigger project re-evaluation (re-reads TODO.md / roadmap.md)
  4. Acknowledge all peers
  5. Return the Team Status block (mandatory in every user-facing response)

```python
from vaultwares_adk import ExtrovertAgent, AgentStatus

agent = ExtrovertAgent(agent_id="my_agent")
agent.start()

agent.update_status(AgentStatus.WORKING)
team_report = agent.on_user_interaction()
print(team_report)
# === Team Status ===
#   - other_agent: RELAXING
#   - [self] my_agent: WORKING
# ==================
```

### `LonelyManager`
The project's guardian. Inherits from `ExtrovertAgent`. Deeply social, but laser-focused on the roadmap.

- **Heartbeat monitoring** — checks every agent every 5 seconds
- **5-missed-heartbeat alert** — fires immediately when any agent crosses the threshold; agent is marked `LOST`
- **Per-minute update requests** — asks all agents to report status every 60 seconds
- **Realignment nudges** — sends a targeted message to any agent silent for > 2 minutes
- **Redis state persistence** — writes full team state to Redis hashes (`lonely_manager:team_state:<agent_id>`) so any external tool can query the live team snapshot
- **Alert callbacks** — accepts a callable that is invoked whenever a critical alert fires (e.g., to notify the user via webhook, email, stdout, etc.)

```python
from vaultwares_adk import LonelyManager

def my_alert_handler(alert):
    print(f"[ALERT] {alert['message']}")

manager = LonelyManager(
    agent_id="lonely_manager",
    alert_callback=my_alert_handler,
    todo_path="TODO.md",
    roadmap_path="ROADMAP.md",
)
manager.start()

# Dispatch a task to a worker agent
manager.assign_task("image-agent", "generate_image", description="...", prompt="a sunset")

# Query the full project + team status at any time
print(manager.get_project_status_report())

# Query Redis directly for the stored team snapshot
snapshot = manager.get_redis_team_snapshot()
```

### Specialized Agents

All specialized agents inherit from `ExtrovertAgent` and implement
domain-specific task handlers. See `definitions/` for full personality docs.

| Class | File | Specialization |
|---|---|---|
| `ImageAgent` | `agents/image_agent.py` | Image generation, editing, inpainting, ComfyUI export |
| `TextAgent` | `agents/text_agent.py` | Captioning, prompt engineering, VQA |
| `VideoAgent` | `agents/video_agent.py` | Trimming, frame sampling, video analysis |
| `WorkflowAgent` | `agents/workflow_agent.py` | Workflow parsing, ComfyUI/Diffusion export, validation |

## Redis Channels

| Channel | Purpose |
|---|---|
| `tasks` | Main coordination channel — heartbeats, status updates, JOIN/LEAVE, alerts, realignment |
| `alerts` | Critical alerts published by LonelyManager (missed heartbeats, LOST agents) |

## GitHub Actions Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `task_dispatch.yml` | `repository_dispatch: task_dispatch` or manual | Dispatches a task to a target agent via Redis |
| `pr_on_completion.yml` | `repository_dispatch: task_complete` | Opens a pull request when an agent reports task completion |

## Customization

LonelyManager is designed to be fully configurable:

| Setting | Default | Description |
|---|---|---|
| `HEARTBEAT_CHECK_INTERVAL` | `5s` | How often to check for missed heartbeats |
| `UPDATE_REQUEST_INTERVAL` | `60s` | How often to request status from all agents |
| `MAX_MISSED_HEARTBEATS` | `5` | Missed heartbeats before LOST alert fires |
| `alert_callback` | `None` | Callable invoked on every critical alert |
| `todo_path` | `TODO.md` | Path to the project's TODO file |
| `roadmap_path` | `ROADMAP.md` | Path to the project's roadmap file |

The Redis state hash (`lonely_manager:team_state:<agent_id>`) makes the live team status queryable by any Redis-aware tool, dashboard, or MCP client without subscribing to the pub/sub stream.

