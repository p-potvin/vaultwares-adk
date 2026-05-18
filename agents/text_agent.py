import time
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from vaultwares_adk import ExtrovertAgent
from vaultwares_adk import AgentStatus


class TextAgent(ExtrovertAgent):
    """
    Text Generation & Manipulation Agent.

    Specializes in:
    - Text generation, captioning, and prompt engineering
    - Visual Question Answering (VQA) and batch operations
    - Prompt enhancement for diffusion models (e.g., Stable Diffusion, SDXL)
    - Text-based workflow creation and conversion to ComfyUI/Diffusion formats

    Inherits the full Extrovert personality: heartbeat every 5 seconds,
    status broadcast every minute, socialization on every user interaction.
    """

    AGENT_TYPE = "text"
    SKILLS = [
        "text_generation",
        "captioning",
        "prompt_engineering",
        "vqa",
        "batch_vqa",
        "prompt_enhancement",
        "workflow_creation",
        "comfyui_export",
    ]

    def __init__(
        self,
        agent_id: str = "text-agent",
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
        """Execute a text processing task based on the task identifier."""
        print(f"📝 [{self.agent_id}] Executing text task: {task}")

        handlers = {
            "generate_text": self._generate_text,
            "generate_caption": self._generate_caption,
            "enhance_prompt": self._enhance_prompt,
            "vqa": self._visual_question_answering,
            "batch_vqa": self._batch_vqa,
            "create_workflow": self._create_text_workflow,
        }

        handler = handlers.get(task)
        if handler:
            handler(details)
        else:
            print(f"⚠️  [{self.agent_id}] Unknown text task: {task}. Logging and continuing.")
            self._log_unknown_task(task, details)

    def _generate_text(self, details: dict):
        """Generate text based on a prompt."""
        prompt = details.get("prompt", "")
        style = details.get("style", "default")
        print(f"✍️  [{self.agent_id}] Generating text | style={style} | prompt='{prompt[:80]}'")
        time.sleep(1)
        result = f"[Generated text for prompt: '{prompt}' in style: '{style}']"
        self._publish_result("generate_text", result)

    def _generate_caption(self, details: dict):
        """Generate a caption for an image or video."""
        source = details.get("source", "unknown")
        caption_style = details.get("caption_style", "detailed")
        print(f"🖼️  [{self.agent_id}] Generating caption | source={source} | style={caption_style}")
        time.sleep(1)
        result = f"[Caption for '{source}' in style '{caption_style}']"
        self._publish_result("generate_caption", result)

    def _enhance_prompt(self, details: dict):
        """Enhance a prompt for use with diffusion models."""
        original_prompt = details.get("prompt", "")
        target_model = details.get("target_model", "sdxl")
        print(f"✨ [{self.agent_id}] Enhancing prompt for {target_model}")
        time.sleep(1)
        enhanced = f"[Enhanced for {target_model}]: {original_prompt}, photorealistic, high quality, 8k"
        self._publish_result("enhance_prompt", enhanced)

    def _visual_question_answering(self, details: dict):
        """Answer a question about an image or video."""
        question = details.get("question", "")
        source = details.get("source", "unknown")
        print(f"❓ [{self.agent_id}] VQA | source={source} | question='{question}'")
        time.sleep(1)
        answer = f"[VQA answer for '{question}' about '{source}']"
        self._publish_result("vqa", answer)

    def _batch_vqa(self, details: dict):
        """Perform VQA on a batch of images/videos."""
        sources = details.get("sources", [])
        question = details.get("question", "")
        print(f"📋 [{self.agent_id}] Batch VQA | {len(sources)} sources | question='{question}'")
        for source in sources:
            time.sleep(0.5)
            print(f"  ✅ VQA completed for: {source}")
        self._publish_result("batch_vqa", f"Batch VQA complete for {len(sources)} sources")

    def _create_text_workflow(self, details: dict):
        """Create a text-based workflow definition."""
        workflow_name = details.get("name", "unnamed_workflow")
        steps = details.get("steps", [])
        print(f"🔧 [{self.agent_id}] Creating text workflow: {workflow_name} ({len(steps)} steps)")
        time.sleep(1)
        self._publish_result("create_workflow", f"Workflow '{workflow_name}' created with {len(steps)} steps")

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
