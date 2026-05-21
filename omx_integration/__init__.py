"""
OMX Integration Layer for VaultWares ADK.

Integrates oh-my-codex (OMX) agentic team orchestration patterns into the
VaultWares multi-agent coordination framework.

This package provides:
- Team orchestration (leader/worker pattern)
- Skill-based workflow routing
- AGENTS.md-driven delegation
- Demo runner for real code generation
- GitHub PR integration for output delivery
"""

from omx_integration.team_orchestrator import TeamOrchestrator
from omx_integration.omx_leader import OMXLeader
from omx_integration.omx_worker import OMXWorker
from omx_integration.skill_router import SkillRouter
from omx_integration.task_queue import TaskQueue, Task, TaskStatus
from omx_integration.mailbox import Mailbox, Message

__all__ = [
    "TeamOrchestrator",
    "OMXLeader",
    "OMXWorker",
    "SkillRouter",
    "TaskQueue",
    "Task",
    "TaskStatus",
    "Mailbox",
    "Message",
]
