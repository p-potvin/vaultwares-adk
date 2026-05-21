"""
vaultwares_adk — importlib shim over the vaultwares-adk submodule.

The canonical source files live in the parent directory of this package (the
git submodule root). Because Python cannot import from a package directory
whose name contains a hyphen, this package (with underscore) loads each module
from the submodule root via importlib and registers it under the
``vaultwares_adk.*`` namespace so that all intra-package relative
imports inside the submodule files resolve correctly.

No code in the submodule root needs to be modified. Consumer code uses::

    import sys, os
    sys.path.insert(0, os.path.abspath("vaultwares-adk"))

    from vaultwares_adk import ExtrovertAgent, LonelyManager, AgentStatus

If the submodule has not been initialised, run::

    git submodule update --init
"""

import importlib.util
import sys
from pathlib import Path

# The submodule root is the parent of this package directory:
#   <submodule_root>/vaultwares_adk/__init__.py  →  parent = <submodule_root>
_SUBMODULE_DIR = Path(__file__).parent.parent.resolve()

_PACKAGE = __name__  # "vaultwares_adk"

# Module load order must respect intra-package dependencies:
#   enums (no deps)
#   → redis_coordinator (no internal deps)
#   → agent_ledger (no internal deps)
#   → agent_base (depends on redis_coordinator, enums)
#   → extrovert_agent (depends on agent_base, enums, agent_ledger)
#   → lonely_manager (depends on extrovert_agent, enums)
_MODULES = [
    "enums",
    "redis_coordinator",
    "agent_ledger",
    "agent_base",
    "extrovert_agent",
    "lonely_manager",
]


def _load_submodule(name: str):
    full_name = f"{_PACKAGE}.{name}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    path = _SUBMODULE_DIR / f"{name}.py"
    if not path.is_file():
        raise ImportError(
            f"Cannot load '{full_name}': '{path}' not found. "
            "The vaultwares-adk submodule may not be initialised — "
            "run `git submodule update --init` and try again."
        )
    spec = importlib.util.spec_from_file_location(full_name, path)
    if spec is None:
        raise ImportError(
            f"Cannot create module spec for '{full_name}' from '{path}'. "
            "Verify that the file is a valid Python source file."
        )
    module = importlib.util.module_from_spec(spec)
    # Register under both the fully-qualified name AND the bare name so that
    # root-level files using absolute imports (e.g. `from extrovert_agent import X`)
    # resolve to the same already-initialised module object rather than being
    # loaded fresh (which would lose __package__ and break relative imports).
    sys.modules[full_name] = module
    sys.modules[name] = module
    module.__package__ = _PACKAGE
    spec.loader.exec_module(module)
    return module


for _name in _MODULES:
    _load_submodule(_name)

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
