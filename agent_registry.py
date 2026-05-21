# Agent Registry for Multi-Agent Coordination

from typing import Dict, Type, Any

class AgentRegistry:
    """
    Central registry for AI agents, their capabilities, and context schemas.
    """
    _agents: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def register(cls, name: str, agent_class: Type, capabilities: str, context_schema: Any):
        cls._agents[name] = {
            'class': agent_class,
            'capabilities': capabilities,
            'context_schema': context_schema,
        }

    @classmethod
    def get_agent(cls, name: str):
        return cls._agents.get(name)

    @classmethod
    def list_agents(cls):
        return list(cls._agents.keys())

    @classmethod
    def describe_agents(cls):
        return {
            name: {
                'capabilities': info['capabilities'],
                'context_schema': getattr(info['context_schema'], '__name__', repr(info['context_schema']))
            }
            for name, info in cls._agents.items()
        }

# Example registration (to be called in agent setup/init):
# AgentRegistry.register('text', TextAgent, 'Text generation, editing, VQA, prompt engineering', TextContext)
# AgentRegistry.register('image', ImageAgent, 'Image generation, editing, masking, inpainting', ImageContext)
# AgentRegistry.register('video', VideoAgent, 'Video generation, editing, analysis', VideoContext)
# AgentRegistry.register('workflow', WorkflowAgent, 'Workflow parsing, export, validation', WorkflowContext)
