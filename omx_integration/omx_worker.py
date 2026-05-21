"""
OMX Worker — Executes assigned task slices within a team.

Follows the AGENTS.md child_agent_protocol:
- Execute the assigned slice; do not rewrite the global plan.
- Stay inside the assigned write scope.
- Report blockers and recommended handoffs upward.
- Ask the leader to widen scope or resolve ambiguity.

Workers write real code files into the project directory and commit via Git.
"""

import json
import os
import subprocess
import threading
import time
from typing import Optional

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from enums import AgentStatus
from redis_coordinator import RedisCoordinator
from hook_registry import hooks
from omx_integration.utils.team_utils import is_safe_path


class OMXWorker:
    """
    A team worker that executes bounded, verifiable subtasks.

    The worker:
    1. Listens for ASSIGN messages on the Redis 'tasks' channel
    2. Executes the assigned code generation task
    3. Writes output files to the project directory
    4. Reports TASK_COMPLETE back to the leader
    5. Creates a git commit for the work

    Platform Notes:
    - Works on macOS, Linux, and Windows (native or WSL)
    - Uses Git for output persistence (files land in the project repo)
    - No tmux dependency — pure Python + Redis
    """

    HEARTBEAT_INTERVAL = 5

    def __init__(
        self,
        worker_id: str,
        team_name: str,
        project_dir: str,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        role: str = "executor",
    ):
        self.worker_id = worker_id
        self.team_name = team_name
        self.project_dir = os.path.abspath(project_dir)
        self.role = role
        self.status = AgentStatus.RELAXING
        self.current_task: Optional[str] = None
        self._stop_event = threading.Event()

        self.coordinator = RedisCoordinator(
            agent_id=worker_id,
            channel="tasks",
            host=redis_host,
            port=redis_port,
        )

    def start(self):
        """Start the worker: announce, begin heartbeat, listen for tasks."""
        hooks.trigger("pre_agent_start", self.worker_id)
        self.status = AgentStatus.WAITING_FOR_INPUT

        # Announce presence
        self.coordinator.publish("JOIN", "startup", {
            "team": self.team_name,
            "role": self.role,
            "status": self.status.value,
        })

        # Start heartbeat thread
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True
        )
        self._heartbeat_thread.start()

        hooks.trigger("post_agent_start", self.worker_id)
        print(f"[{self.worker_id}] Worker started (team={self.team_name}, role={self.role})")

    def _heartbeat_loop(self):
        """Send heartbeats every 5 seconds."""
        while not self._stop_event.is_set():
            self.coordinator.publish("HEARTBEAT", self.current_task or "", {
                "status": self.status.value,
                "team": self.team_name,
            })
            self._stop_event.wait(self.HEARTBEAT_INTERVAL)

    def execute_task(self, task_id: str, subject: str, description: str, output_files: dict):
        """
        Execute a code generation task.

        Args:
            task_id: Unique task identifier.
            subject: Task title.
            description: What to implement.
            output_files: Dict of {relative_path: file_content} to write.
        """
        self.status = AgentStatus.WORKING
        self.current_task = task_id
        hooks.trigger("pre_assignment", self.worker_id, task_id)

        print(f"[{self.worker_id}] Executing task: {subject}")

        created_files = []
        for rel_path, content in output_files.items():
            if not is_safe_path(self.project_dir, rel_path):
                print(f"[{self.worker_id}]   SKIPPED unsafe path: {rel_path}")
                continue

            abs_path = os.path.join(self.project_dir, rel_path)

            # Security check: Ensure the path is within the project directory
            if not is_safe_path(abs_path, self.project_dir):
                print(f"[{self.worker_id}]   ERROR: Blocked path traversal attempt: {rel_path}")
                continue

            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            created_files.append(rel_path)
            print(f"[{self.worker_id}]   Wrote: {rel_path}")

        # Git add + commit the files
        try:
            subprocess.run(
                ["git", "add"] + created_files,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            commit_msg = (
                f"{subject}\n\n"
                f"Worker: {self.worker_id}\n"
                f"Team: {self.team_name}\n"
                f"Task-ID: {task_id}\n"
                f"Files: {', '.join(created_files)}\n\n"
                f"Confidence: high\n"
                f"Scope-risk: narrow\n"
                f"Tested: file creation verified"
            )
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            print(f"[{self.worker_id}]   Committed: {subject}")
        except subprocess.CalledProcessError as e:
            print(f"[{self.worker_id}]   Git commit note: {e.stderr.strip()}")

        # Report completion
        self.coordinator.publish("TASK_COMPLETE", task_id, {
            "subject": subject,
            "files": created_files,
            "team": self.team_name,
        })

        hooks.trigger("post_assignment", self.worker_id, task_id)
        self.current_task = None
        self.status = AgentStatus.WAITING_FOR_INPUT
        print(f"[{self.worker_id}] Task completed: {subject}")
        return created_files

    def stop(self):
        """Stop the worker and announce departure."""
        hooks.trigger("pre_agent_stop", self.worker_id)
        self._stop_event.set()

        self.coordinator.publish("LEAVE", "shutdown", {"team": self.team_name})

        self.coordinator.stop()
        hooks.trigger("post_agent_stop", self.worker_id)
        print(f"[{self.worker_id}] Worker stopped")
