"""
Team Orchestrator — High-level interface for running OMX-style agentic teams.

This is the main entry point for integrating oh-my-codex team patterns into
VaultWares ADK. It manages the full team lifecycle:

  1. Team creation (leader + workers)
  2. Plan decomposition
  3. Task assignment and execution
  4. Verification
  5. PR creation

Communication Methods:
  - Redis pub/sub for real-time inter-agent messaging
  - Mailbox system for structured, durable messages
  - GitHub PRs for output delivery to the user

Platform Compatibility:
  - CLI-based: works from any terminal (bash, PowerShell, etc.)
  - IDE-compatible: can be invoked from VS Code tasks, PyCharm run configs, etc.
  - Windows: Works natively with Python + Redis (no WSL required for core features)
  - macOS/Linux: Full support including optional tmux integration
  - WSL: Fully supported as a Linux environment

Program Interface:
  - Primary: CLI via Python scripts (demo/run_demo.py)
  - Secondary: Python API for programmatic use
  - IDE: VS Code launch.json configs provided
  - Communication: Redis channels + GitHub PRs for human review
"""

import json
import os
import time
from typing import Optional

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from omx_integration.omx_leader import OMXLeader
from omx_integration.omx_worker import OMXWorker
from omx_integration.task_queue import TaskQueue, TaskStatus
from omx_integration.mailbox import Mailbox
from omx_integration.skill_router import SkillRouter


class TeamOrchestrator:
    """
    High-level orchestrator that manages an entire team session.

    Usage:
        orchestrator = TeamOrchestrator(
            team_name="feature-auth",
            project_dir="/path/to/repo",
            worker_count=3,
        )
        orchestrator.setup()
        orchestrator.run_pipeline(tasks=[...])
        orchestrator.teardown()
    """

    def __init__(
        self,
        team_name: str = "omx-team",
        project_dir: str = ".",
        worker_count: int = 3,
        worker_roles: Optional[list] = None,
        redis_host: str = "localhost",
        redis_port: int = 6379,
    ):
        self.team_name = team_name
        self.project_dir = os.path.abspath(project_dir)
        self.worker_count = worker_count
        self.worker_roles = worker_roles or ["executor"] * worker_count
        self.redis_host = redis_host
        self.redis_port = redis_port

        self.leader: Optional[OMXLeader] = None
        self.workers: list[OMXWorker] = []

    def setup(self):
        """Create and start the leader and all workers."""
        print(f"\n{'='*60}")
        print(f"  OMX Team Setup: {self.team_name}")
        print(f"  Workers: {self.worker_count}")
        print(f"  Project: {self.project_dir}")
        print(f"{'='*60}\n")

        # Create leader
        self.leader = OMXLeader(
            leader_id="leader-fixed",
            team_name=self.team_name,
            project_dir=self.project_dir,
            redis_host=self.redis_host,
            redis_port=self.redis_port,
        )
        self.leader.start()

        # Create workers
        for i in range(self.worker_count):
            role = self.worker_roles[i] if i < len(self.worker_roles) else "executor"
            
            if role == "cheddar-bob":
                from omx_integration.cheddar_bob_worker import CheddarBobWorker
                worker_cls = CheddarBobWorker
            else:
                worker_cls = OMXWorker

            worker = worker_cls(
                worker_id=f"worker-{i+1}",
                team_name=self.team_name,
                project_dir=self.project_dir,
                redis_host=self.redis_host,
                redis_port=self.redis_port,
                role=role,
            )
            worker.start()
            self.workers.append(worker)
            self.leader.register_worker(f"worker-{i+1}", role)

        print(f"\nTeam {self.team_name} is ready with {len(self.workers)} workers.\n")

    def run_pipeline(self, tasks: list) -> dict:
        """
        Run the full OMX pipeline: plan -> assign -> execute -> verify.

        Args:
            tasks: List of dicts with:
                - subject: Task title
                - description: What to implement
                - output_files: Dict of {path: content} for worker to write

        Returns:
            Verification report dict.
        """
        if not self.leader:
            raise RuntimeError("Call setup() before run_pipeline()")

        # Stage 1: Plan
        print(f"\n--- Stage 1: team-plan ---")
        created_tasks = self.leader.create_plan([
            {"subject": t["subject"], "description": t.get("description", "")}
            for t in tasks
        ])

        # Stage 2: Assign
        print(f"\n--- Stage 2: team-exec (assign + execute) ---")
        assignments = []
        for i, task_obj in enumerate(created_tasks):
            worker_idx = i % len(self.workers)
            assignments.append({
                "task_id": task_obj.task_id,
                "worker_id": f"worker-{worker_idx + 1}",
            })
        self.leader.assign_tasks(assignments)

        # Stage 3: Execute (workers write files)
        print(f"\n--- Stage 3: Execution ---")
        for i, task_spec in enumerate(tasks):
            worker_idx = i % len(self.workers)
            worker = self.workers[worker_idx]
            task_obj = created_tasks[i]

            # Worker executes and writes files
            worker.execute_task(
                task_id=task_obj.task_id,
                subject=task_spec["subject"],
                description=task_spec.get("description", ""),
                output_files=task_spec.get("output_files", {}),
            )

            # Record completion with leader
            task_refreshed = self.leader.task_queue.get_task(task_obj.task_id)
            if task_refreshed and task_refreshed.claim_token:
                self.leader.record_completion(
                    task_obj.task_id,
                    task_refreshed.claim_token,
                    result=f"Files written: {list(task_spec.get('output_files', {}).keys())}",
                )

        # Stage 4: Verify
        print(f"\n--- Stage 4: team-verify ---")
        report = self.leader.verify_completion()

        print(f"\n--- Pipeline Report ---")
        print(self.leader.get_team_report())

        return report

    def teardown(self):
        """Shut down the team."""
        print(f"\n--- Teardown ---")
        for worker in self.workers:
            worker.stop()
        if self.leader:
            self.leader.shutdown()
            self.leader.cleanup()
        print(f"Team {self.team_name} shut down.\n")
