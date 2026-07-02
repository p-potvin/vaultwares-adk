import importlib


def test_spawn_agent_skill_imports_public_helpers():
    module = importlib.import_module("skills.spawn_agent_skill")

    assert callable(module.spawn_subagent)
    assert callable(module.remove_subagent)
