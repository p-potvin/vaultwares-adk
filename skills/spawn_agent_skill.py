"""
SpawnAgentSkill — Async subagent spawning and management for VaultWares agents.

This skill provides reusable async functions for spawning, tracking, and removing
subagents in an isolated context. It is designed to be used by Manager agents.

Usage:
    from skills.spawn_agent_skill import spawn_subagent, remove_subagent
    subagent_id = await spawn_subagent(manager, agent_class, *args, **kwargs)
    await remove_subagent(manager, subagent_id)
"""

import asyncio
import uuid

async def spawn_subagent(manager, agent_class, *args, **kwargs):
    """
    Spawn a subagent as an asyncio Task. Each subagent gets a unique agent_id.
    Registers the subagent in manager.subagents.
    """
    subagent_id = f"subagent-{uuid.uuid4().hex[:8]}"
    agent = agent_class(subagent_id, *args, **kwargs)
    task = asyncio.create_task(agent.run())
    manager.subagents[subagent_id] = task
    manager.coordinator.publish('SPAWN', 'subagent_spawned', {'subagent_id': subagent_id})
    return subagent_id

async def remove_subagent(manager, subagent_id):
    """
    Cancel and remove a subagent by id.
    """
    task = manager.subagents.get(subagent_id)
    if task:
        task.cancel()
        manager.coordinator.publish('REMOVE', 'subagent_removed', {'subagent_id': subagent_id})
        del manager.subagents[subagent_id]
