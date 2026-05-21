import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from vaultwares_adk import ExtrovertAgent


class VideoAgent(ExtrovertAgent):
    """
    Video Generation & Manipulation Agent.

    Specializes in:
    - Video sampling, trimming, resizing, and frame-level processing
    - Per-frame effects, overlays, and stabilization
    - Video description and per-frame captioning
    - Workflow creation and export to ComfyUI/Diffusion formats

    Inherits the full Extrovert personality: heartbeat every 5 seconds,
    status broadcast every minute, socialization on every user interaction.
    """

    AGENT_TYPE = "video"
    SKILLS = [
        "video_trimming",
        "video_resizing",
        "frame_sampling",
        "per_frame_effects",
        "video_captioning",
        "video_analysis",
        "workflow_creation",
        "comfyui_export",
    ]

    def __init__(
        self,
        agent_id: str = "video-agent",
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
        """Execute a video processing task using ffmpeg."""
        print(f"[VideoAgent] [{self.agent_id}] Executing video task: {task}")

        handlers = {
            "trim_video": self._trim_video,
            "resize_video": self._resize_video,
            "sample_frames": self._sample_frames,
            "apply_effects": self._apply_effects,
            "generate_caption": self._generate_video_caption,
            "analyze_video": self._analyze_video,
            "create_workflow": self._create_video_workflow,
            "export_comfyui": self._export_comfyui,
        }

        handler = handlers.get(task)
        if handler:
            try:
                handler(details)
            except Exception as e:
                print(f"[ERROR] [{self.agent_id}] Error in {task}: {e}")
                self._publish_result(task, f"ERROR: {str(e)}")
        else:
            print(f"[WARN] [{self.agent_id}] Unknown video task: {task}.")
            self._log_unknown_task(task, details)

    def _get_ffmpeg_path(self):
        """Return the path to the ffmpeg executable."""
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("ffmpeg not found on PATH")
        return ffmpeg

    def _trim_video(self, details: dict):
        """Trim a video to a specified time range using ffmpeg."""
        source = details.get("source")
        output = details.get("output", f"trimmed_{os.path.basename(source)}")
        start = details.get("start_time", "00:00:00")
        duration = details.get("duration")
        
        if not source or not os.path.exists(source):
            raise FileNotFoundError(f"Source video not found: {source}")

        cmd = [
            self._get_ffmpeg_path(), "-y",
            "-ss", str(start),
            "-i", source
        ]
        if duration:
            cmd += ["-t", str(duration)]
        
        cmd += ["-c", "copy", output]

        print(f"[VideoAgent] [{self.agent_id}] Running ffmpeg trim: {' '.join(cmd)}")
        self._run_subprocess(cmd)
        self._publish_result("trim_video", f"Trimmed to {output}")

    def _resize_video(self, details: dict):
        """Resize a video using ffmpeg."""
        source = details.get("source")
        output = details.get("output", f"resized_{os.path.basename(source)}")
        width = details.get("width", 1280)
        height = details.get("height", 720)
        
        if not source or not os.path.exists(source):
            raise FileNotFoundError(f"Source video not found: {source}")

        cmd = [
            self._get_ffmpeg_path(), "-y",
            "-i", source,
            "-vf", f"scale={width}:{height}",
            "-c:a", "copy",
            output
        ]

        print(f"[VideoAgent] [{self.agent_id}] Running ffmpeg resize: {' '.join(cmd)}")
        self._run_subprocess(cmd)
        self._publish_result("resize_video", f"Resized to {output} ({width}x{height})")

    def _sample_frames(self, details: dict):
        """Extract frames from a video at a specific FPS into a directory."""
        source = details.get("source")
        output_dir = details.get("output_dir", "frames")
        fps = details.get("fps", 2)

        if not source or not os.path.exists(source):
            raise FileNotFoundError(f"Source video not found: {source}")

        os.makedirs(output_dir, exist_ok=True)
        for file_name in os.listdir(output_dir):
            if file_name.lower().endswith(".png"):
                os.remove(os.path.join(output_dir, file_name))

        output_pattern = os.path.join(output_dir, "frame_%04d.png")
        cmd = [
            self._get_ffmpeg_path(), "-y",
            "-i", source,
            "-vf", f"fps={fps}",
            "-q:v", "2",
            output_pattern
        ]

        print(f"[VideoAgent] [{self.agent_id}] Running ffmpeg sampling: {' '.join(cmd)}")
        self._run_subprocess(cmd)

        frame_count = len([f for f in os.listdir(output_dir) if f.endswith(".png")])
        self._publish_result("sample_frames", f"Extracted {frame_count} frames to {output_dir}")

    def _apply_effects(self, details: dict):
        """Apply per-frame effects (placeholder for now, could be ffmpeg filters)."""
        source = details.get("source", "unknown")
        effects = details.get("effects", [])
        print(f"[VideoAgent] [{self.agent_id}] Applying effects (STUB) | source={source} | effects={effects}")
        self._publish_result("apply_effects", f"STUB: Applied {len(effects)} effects")

    def _generate_video_caption(self, details: dict):
        """Generate a caption (placeholder)."""
        source = details.get("source", "unknown")
        self._publish_result("generate_caption", f"STUB: Caption for {source}")

    def _analyze_video(self, details: dict):
        """Perform analysis (placeholder)."""
        source = details.get("source", "unknown")
        self._publish_result("analyze_video", f"STUB: Analysis for {source}")

    def _create_video_workflow(self, details: dict):
        """Create a video processing workflow (placeholder)."""
        workflow_name = details.get("name", "unnamed_workflow")
        self._publish_result("create_workflow", f"STUB: Workflow {workflow_name} created")

    def _export_comfyui(self, details: dict):
        """Export to ComfyUI (placeholder)."""
        workflow_name = details.get("workflow_name", "unnamed")
        self._publish_result("export_comfyui", f"STUB: ComfyUI export for {workflow_name}")

    def _log_unknown_task(self, task: str, details: dict):
        """Log an unrecognized task for debugging."""
        print(f"[VideoAgent] [{self.agent_id}] Unknown task '{task}' - details: {details}")

    def _publish_result(self, task: str, result: str):
        """Publish a task result back to the Redis channel."""
        self.coordinator.publish(
            "RESULT",
            task,
            {
                "agent": self.agent_id,
                "task": task,
                "result": result,
                "timestamp": time.time()
            },
        )
        print(f"[VideoAgent] [{self.agent_id}] Result published for task '{task}'")

    def _run_subprocess(self, cmd: list[str], timeout: int = 1800):
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)
        if completed.stdout:
            print(completed.stdout.strip())
        if completed.stderr:
            print(completed.stderr.strip())
        if completed.returncode != 0:
            raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(cmd)}")
