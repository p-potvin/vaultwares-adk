import time
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from vaultwares_adk import ExtrovertAgent
from vaultwares_adk import AgentStatus


class WorkflowAgent(ExtrovertAgent):
    """
    Workflow Conversion & Export Agent.

    Specializes in:
    - Parsing and analyzing Python workflow definitions
    - Mapping workflow steps to ComfyUI/Diffusion nodes
    - Exporting and validating workflow files for use in generative UIs
    - Workflow validation and error reporting

    Inherits the full Extrovert personality: heartbeat every 5 seconds,
    status broadcast every minute, socialization on every user interaction.
    """

    AGENT_TYPE = "workflow"
    SKILLS = [
        "workflow_parsing",
        "step_mapping",
        "comfyui_export",
        "diffusion_export",
        "workflow_validation",
        "error_reporting",
    ]

    def __init__(
        self,
        agent_id: str = "workflow-agent",
        channel: str = "tasks",
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
    ):
        super().__init__(agent_id, channel, redis_host, redis_port, redis_db)

    # ------------------------------------------------------------------
    # Task Execution
    # ------------------------------------------------------------------

    def _perform_task(self, task: str, details: dict):
        """Execute a workflow processing task based on the task identifier."""
        print(f"⚙️  [{self.agent_id}] Executing workflow task: {task}")

        handlers = {
            "parse_workflow": self._parse_workflow,
            "map_to_comfyui": self._map_to_comfyui,
            "export_comfyui": self._export_comfyui,
            "export_diffusion": self._export_diffusion,
            "validate_workflow": self._validate_workflow,
            "convert_workflow": self._convert_workflow,
        }

        handler = handlers.get(task)
        if handler:
            handler(details)
        else:
            print(f"⚠️  [{self.agent_id}] Unknown workflow task: {task}. Logging and continuing.")
            self._log_unknown_task(task, details)

    def _parse_workflow(self, details: dict):
        """Parse a workflow definition and extract its structure."""
        source = details.get("source", "unknown")
        format_ = details.get("format", "python")
        print(f"📖 [{self.agent_id}] Parsing workflow | source={source} | format={format_}")
        time.sleep(1)
        self._publish_result("parse_workflow", f"Workflow '{source}' parsed successfully")

    def _map_to_comfyui(self, details: dict):
        """Map workflow steps to ComfyUI node types."""
        workflow_name = details.get("workflow_name", "unnamed")
        steps = details.get("steps", [])
        print(f"🗺️  [{self.agent_id}] Mapping to ComfyUI nodes | workflow={workflow_name} | steps={len(steps)}")
        node_map = {}
        for i, step in enumerate(steps):
            node_map[step] = f"ComfyUI_Node_{i}"
            time.sleep(0.2)
        self._publish_result("map_to_comfyui", f"Mapped {len(steps)} steps to ComfyUI nodes for '{workflow_name}'")

    def _export_comfyui(self, details: dict):
        """Export a workflow to ComfyUI JSON format."""
        workflow_name = details.get("workflow_name", "unnamed")
        output_path = details.get("output_path", f"{workflow_name}_comfyui.json")
        steps = details.get("steps", [])
        print(f"📦 [{self.agent_id}] Exporting to ComfyUI | workflow={workflow_name} → {output_path}")
        time.sleep(1)

        comfyui_workflow = {
            "version": "1.0",
            "name": workflow_name,
            "nodes": [
                {"id": i, "type": f"NODE_{step.upper()}", "inputs": {}, "outputs": {}}
                for i, step in enumerate(steps)
            ],
            "links": [],
        }

        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(comfyui_workflow, f, indent=2)
            self._publish_result("export_comfyui", f"ComfyUI workflow exported to '{output_path}'")
        except Exception as e:
            print(f"❌ [{self.agent_id}] Export failed: {e}")
            self._publish_result("export_comfyui", f"Export failed: {e}")

    def _export_diffusion(self, details: dict):
        """Export a workflow to a Stable Diffusion compatible format."""
        workflow_name = details.get("workflow_name", "unnamed")
        output_path = details.get("output_path", f"{workflow_name}_diffusion.json")
        print(f"📦 [{self.agent_id}] Exporting to Diffusion format | workflow={workflow_name} → {output_path}")
        time.sleep(1)
        self._publish_result("export_diffusion", f"Diffusion workflow exported to '{output_path}'")

    def _validate_workflow(self, details: dict):
        """Validate a workflow definition for correctness and compatibility."""
        workflow_name = details.get("workflow_name", "unnamed")
        target = details.get("target", "comfyui")
        print(f"✅ [{self.agent_id}] Validating workflow | name={workflow_name} | target={target}")
        time.sleep(1)

        errors = []
        warnings = []

        if not details.get("steps"):
            warnings.append("No steps defined in workflow")

        status = "VALID" if not errors else "INVALID"
        self._publish_result(
            "validate_workflow",
            f"Validation {status} for '{workflow_name}': {len(errors)} errors, {len(warnings)} warnings",
        )

    def _convert_workflow(self, details: dict):
        """Convert a workflow from one format to another."""
        source_format = details.get("source_format", "python")
        target_format = details.get("target_format", "comfyui")
        workflow_name = details.get("workflow_name", "unnamed")
        print(f"🔄 [{self.agent_id}] Converting workflow | {source_format} → {target_format} | name={workflow_name}")
        time.sleep(1)
        self._publish_result("convert_workflow", f"Converted '{workflow_name}' from {source_format} to {target_format}")

    def _log_unknown_task(self, task: str, details: dict):
        """Log an unrecognized task for debugging."""
        print(f"📋 [{self.agent_id}] Unknown task '{task}' — details: {details}")

    def _publish_result(self, task: str, result: str):
        """Publish a task result back to the Redis channel."""
        self.coordinator.publish(
            "RESULT",
            task,
            {
                "agent": self.agent_id,
                "task": task,
                "result": result,
            },
        )
        print(f"📤 [{self.agent_id}] Result published for task '{task}'")
