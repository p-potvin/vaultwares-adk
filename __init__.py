"""Compatibility imports for the vendored vaultwares_adk package."""
# ruff: noqa: E402

from pathlib import Path
import sys

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from .enums import AgentStatus
from .redis_coordinator import RedisCoordinator
from .agent_base import AgentBase
from .extrovert_agent import ExtrovertAgent, _GitHubSkills as GitHubSkills
from .lonely_manager import LonelyManager

__all__ = [
    "AgentStatus",
    "RedisCoordinator",
    "AgentBase",
    "ExtrovertAgent",
    "LonelyManager",
    "GitHubSkills",
]
