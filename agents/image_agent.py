import time
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from vaultwares_adk import ExtrovertAgent
from vaultwares_adk import AgentStatus


class ImageAgent(ExtrovertAgent):
    """
    Image Generation & Manipulation Agent.

    Specializes in:
    - Image generation and editing (resize, crop, rotate, sharpen, blur)
    - Mask creation, inpainting, outpainting, and healing
    - Prompt generation and enhancement for image diffusion models
    - Workflow creation and export to ComfyUI/Diffusion formats

    Inherits the full Extrovert personality: heartbeat every 5 seconds,
    status broadcast every minute, socialization on every user interaction.
    """

    AGENT_TYPE = "image"
    SKILLS = [
        "image_generation",
        "image_editing",
        "masking",
        "inpainting",
        "outpainting",
        "prompt_generation",
        "workflow_creation",
        "comfyui_export",
    ]

    def __init__(
        self,
        agent_id: str = "image-agent",
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
        """Execute an image processing task based on the task identifier."""
        print(f"🖼️  [{self.agent_id}] Executing image task: {task}")

        handlers = {
            "generate_image": self._generate_image,
            "edit_image": self._edit_image,
            "create_mask": self._create_mask,
            "inpaint": self._inpaint,
            "outpaint": self._outpaint,
            "create_workflow": self._create_image_workflow,
            "export_comfyui": self._export_comfyui,
        }

        handler = handlers.get(task)
        if handler:
            handler(details)
        else:
            print(f"⚠️  [{self.agent_id}] Unknown image task: {task}. Logging and continuing.")
            self._log_unknown_task(task, details)

    def _generate_image(self, details: dict):
        """Generate an image from a prompt."""
        prompt = details.get("prompt", "")
        model = details.get("model", "sdxl")
        width = details.get("width", 1024)
        height = details.get("height", 1024)
        print(f"🎨 [{self.agent_id}] Generating image | model={model} | {width}x{height}")
        print(f"   Prompt: '{prompt[:80]}'")
        time.sleep(2)
        result = f"[Image generated: {width}x{height} using {model} | prompt: '{prompt[:40]}...']"
        self._publish_result("generate_image", result)

    def _edit_image(self, details: dict):
        """Apply edits to an image (resize, crop, rotate, sharpen, blur, etc.)."""
        source = details.get("source", "unknown")
        operations = details.get("operations", [])
        print(f"✂️  [{self.agent_id}] Editing image: {source} | operations: {operations}")
        for op in operations:
            time.sleep(0.3)
            print(f"  ✅ Applied: {op}")
        self._publish_result("edit_image", f"Image '{source}' edited with {len(operations)} operations")

    def _create_mask(self, details: dict):
        """Create a segmentation mask for an image region."""
        source = details.get("source", "unknown")
        region = details.get("region", "auto")
        print(f"🎭 [{self.agent_id}] Creating mask | source={source} | region={region}")
        time.sleep(1)
        self._publish_result("create_mask", f"Mask created for '{source}' region '{region}'")

    def _inpaint(self, details: dict):
        """Inpaint a masked region of an image."""
        source = details.get("source", "unknown")
        prompt = details.get("prompt", "")
        mask = details.get("mask", "auto")
        print(f"🖌️  [{self.agent_id}] Inpainting | source={source} | mask={mask}")
        print(f"   Prompt: '{prompt[:80]}'")
        time.sleep(2)
        self._publish_result("inpaint", f"Inpainting complete for '{source}'")

    def _outpaint(self, details: dict):
        """Extend an image beyond its original borders."""
        source = details.get("source", "unknown")
        direction = details.get("direction", "all")
        pixels = details.get("pixels", 256)
        print(f"🔲 [{self.agent_id}] Outpainting | source={source} | direction={direction} | +{pixels}px")
        time.sleep(2)
        self._publish_result("outpaint", f"Outpainting complete for '{source}' — extended {pixels}px {direction}")

    def _create_image_workflow(self, details: dict):
        """Create an image processing workflow definition."""
        workflow_name = details.get("name", "unnamed_workflow")
        steps = details.get("steps", [])
        print(f"🔧 [{self.agent_id}] Creating image workflow: {workflow_name} ({len(steps)} steps)")
        time.sleep(1)
        self._publish_result("create_workflow", f"Image workflow '{workflow_name}' created with {len(steps)} steps")

    def _export_comfyui(self, details: dict):
        """Export a workflow to ComfyUI JSON format."""
        workflow_name = details.get("workflow_name", "unnamed")
        output_path = details.get("output_path", f"{workflow_name}.json")
        print(f"📦 [{self.agent_id}] Exporting to ComfyUI: {workflow_name} → {output_path}")
        time.sleep(1)
        self._publish_result("export_comfyui", f"ComfyUI export complete: {output_path}")

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
