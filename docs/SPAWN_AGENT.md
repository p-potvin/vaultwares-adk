# Spawn Agent Flow (The Manager Routine)

This document describes the "Manager" routine used to delegate specific, bounded tasks to worker agents (Gemini or Codex) using the `spawn-agent` skill.

## 🎯 Purpose

The goal of this flow is to keep the orchestrator's context clean and delegate implementation, research, or bug-fixing tasks to independent worker agents. This improves throughput and prevents context pollution in long-running projects.

## 🏗️ Architecture

The flow relies on three main components:

1. **Task Templates**: Pre-structured markdown files that define the goal, architecture, file map, and steps for a task.
2. **Spawn Script (`spawn-agent.sh`)**: A bash script that initiates a headless agent session with the provided prompt or task file.
3. **Execution Agent**: A worker CLI (Gemini or Codex) running in `auto_edit` or `full-auto` mode.

## 📋 Step-by-Step Flow

### 1. Task Definition

The orchestrator identifies a sub-task that can be handled independently. A project-specific task file is created in `.agent/spawn_agent_tasks/` using a template.

Example: `unified-fetcher-task.md`

### 2. Initiation

The orchestrator calls the `spawn-agent.sh` script via the shell.

**Recommended Command (Windows/Git Bash):**

```powershell
& "C:\Program Files\Git\bin\bash.exe" "$CODEX_HOME/skills/spawn-agent/scripts/spawn-agent.sh" --codex --auto-edit -f ".agent/spawn_agent_tasks/my-task.md"
```

### 3. Execution

The script pipes the prompt into the chosen CLI.

- **Codex**: Runs in `auto-edit` mode (approves edits automatically, asks for others).
- **Gemini**: Runs in `auto_edit` mode.

The worker agent executes the steps outlined in the task file, modifying files and verifying its work.

### 4. Monitoring

The orchestrator monitors the background process using `command_status`. A log file is generated for each run in `.agent/spawn_agent_tasks/output-YYYYMMDD-HHMMSS.log`.

### 5. Verification & Integration

Once the worker agent completes the task (Exit code 0), the orchestrator reviews the changes and integrates them into the main branch or performs final verification.

## 🔧 Maintenance

To update the worker agents, run:

- **Codex**: `npm install -g @openai/codex@latest`
- **Gemini**: `npm install -g @google/gemini-cli@latest`

## 🚫 Troubleshooting

- **403 Forbidden (Gemini)**: Check API key permissions or CLI authentication status.
- **Sandbox Error 1056 (Windows)**: Ensure the Windows Sandbox feature is correctly configured or run without strict sandboxing if necessary.
- **Outdated CLI (Codex)**: Ensure version is `0.130.0` or higher to support `gpt-5.5`.
