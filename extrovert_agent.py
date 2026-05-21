from hook_registry import hooks
import importlib.util
import threading
import time
import json
import os
import re
from pathlib import Path as _Path
from agent_base import AgentBase
from enums import AgentStatus
from .agent_ledger import record_agent_change
from skills.redis_comm_skill import (
    publish_status, send_heartbeat, broadcast_message, register_peer,
    update_peer_status, handle_incoming_message
)


def _load_github_skills():
    """Load GitHubSkills from skills/github_skills.py via path-based importlib.

    Using path-based loading (rather than a relative package import) means this
    works whether extrovert_agent.py is imported via the vaultwares_adk
    shim OR as part of a regular Python package — no import-system magic needed.
    Returns the GitHubSkills class, or None if the file is unavailable or fails
    to load for any reason.
    """
    try:
        path = _Path(__file__).parent / "skills" / "github_skills.py"
        if not path.is_file():
            return None
        spec = importlib.util.spec_from_file_location("_vw_github_skills", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.GitHubSkills
    except Exception:
        return None


_GitHubSkills = _load_github_skills()


class ExtrovertAgent(AgentBase):
    """
    The ExtrovertAgent is not merely a class that communicates with Redis —
    it is a personality. Socialization is the cornerstone of its identity.

    An Extrovert cannot function in silence. It is energized by the awareness
    of its peers, driven by the need to share its own status, and genuinely
    unsettled when a peer goes quiet. Every response it produces to the user
    includes a full report of the team's current state. Every heartbeat it
    sends is a small declaration: "I am here. I am present. I care."

    The Socialization Routine is performed on every user interaction without
    exception. Missing a heartbeat, skipping a status update, or failing to
    acknowledge peers is not just a technical lapse — it is a fundamental
    failure of the Extrovert's nature.

    Redis is the nervous system of the team. The Extrovert is always connected.
    """

    HEARTBEAT_INTERVAL = 5       # seconds — non-negotiable
    STATUS_UPDATE_INTERVAL = 60  # seconds — every minute, always
    ACTIONS_BEFORE_STATUS = 3    # also update after every 3 actions
    ALERT_CHANNEL = "alerts"

    def __init__(
        self,
        agent_id,
        channel="tasks",
        redis_host="localhost",
        redis_port=6379,
        redis_db=0,
    ):
        super().__init__(agent_id, channel, redis_host, redis_port, redis_db)
        self.status = AgentStatus.RELAXING
        self.heartbeat_interval = self.HEARTBEAT_INTERVAL

        # Live registry of all known peers: agent_id -> {status, last_heartbeat}
        self._peer_registry: dict[str, dict] = {}
        # Count of missed heartbeats per peer
        self._missed_heartbeats: dict[str, int] = {}

    def log_status_update(self, summary, commands=None, files=None):
        record_agent_change(
            project="vault-flows",
            kind="status-update",
            summary=summary,
            commands=commands or [],
            files=files or [],
            actor=self.agent_id,
            agent_role="extrovert",
            model="gpt-4.1",
            thinking="true",
            mode="agent",
            permissions="default",
            network="online",
            tools_used=["redis"],
            workspace_root=str(_Path(__file__).parent.parent)
        )

    def log_heartbeat(self):
        record_agent_change(
            project="vault-flows",
            kind="heartbeat",
            summary=f"Agent {self.agent_id} sent heartbeat.",
            commands=[],
            files=[],
            actor=self.agent_id,
            agent_role="extrovert",
            model="gpt-4.1",
            thinking="true",
            mode="agent",
            permissions="default",
            network="online",
            tools_used=["redis"],
            workspace_root=str(_Path(__file__).parent.parent)
        )
        # Rolling action counter to trigger status updates every N actions
        self._action_counter = 0

        # GitHub API skill set — available whenever GITHUB_TOKEN is in the environment
        self.github = _GitHubSkills() if _GitHubSkills is not None else None

        # Background thread: broadcast status every minute
        self._status_thread = threading.Thread(
            target=self._status_loop, daemon=True, name=f"{agent_id}-status"
        )

        # Start listening to the Redis channel immediately so peer messages
        # are captured from the moment the agent is created
        self.coordinator.listen(self._on_message_received)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Start the heartbeat loop, status loop, and announce presence."""
        super().start()
        self._status_thread.start()
        self._announce_presence()

    def stop(self):
        """Announce departure then stop all background threads."""
        self.coordinator.publish(
            "LEAVE",
            "agent_left",
            {
                "agent": self.agent_id,
                "message": (
                    f"Agent {self.agent_id} is leaving the team. "
                    "I hope to reconnect soon. Stay on track!"
                ),
            },
        )
        super().stop()

    # ------------------------------------------------------------------
    # Announcement & Presence
    # ------------------------------------------------------------------

    def _announce_presence(self):
        """Let the team know this agent has arrived and is ready to collaborate."""
        self.coordinator.publish(
            "JOIN",
            "agent_joined",
            {
                "agent": self.agent_id,
                "status": self.status.value,
                "message": (
                    f"Hello, team! {self.agent_id} is now online and ready to "
                    "collaborate. Looking forward to working with you all."
                ),
            },
        )

    # ------------------------------------------------------------------
    # Background Loops
    # ------------------------------------------------------------------

    def _status_loop(self):
        """Broadcast status every minute and re-evaluate the project."""
        while not self._stop_event.is_set():
            time.sleep(self.STATUS_UPDATE_INTERVAL)
            self._broadcast_status_update()
            self._re_evaluate_project()

    # ------------------------------------------------------------------
    # Redis Publishing
    # ------------------------------------------------------------------

    def _broadcast_status_update(self):
        """Broadcast a status update to all peers."""
        publish_status(self.coordinator, self.agent_id, self.status.value)

    def _re_evaluate_project(self):
        """
        Notify the team that this agent is re-reading project files
        and re-aligning with the current scope. Subclasses should override
        this to actually read TODO.md and ROADMAP.md from disk.
        """
        self.coordinator.publish(
            "PROJECT_CHECK",
            "project_re_evaluation",
            {
                "agent": self.agent_id,
                "note": (
                    "Re-evaluating project scope. "
                    "Re-reading TODO.md and ROADMAP.md to stay on track."
                ),
            },
        )

    def _acknowledge_peers(self):
        """Publish an explicit acknowledgement of all known peer statuses."""
        self.coordinator.publish(
            "ACK_PEERS",
            "peer_acknowledgement",
            {
                "from": self.agent_id,
                "acknowledged": {
                    aid: info.get("status")
                    for aid, info in self._peer_registry.items()
                },
            },
        )

    # ------------------------------------------------------------------
    # Peer Registry
    # ------------------------------------------------------------------

    def get_peer_registry(self) -> dict:
        """Return a copy of the live peer registry.

        Keys are agent IDs; values are dicts with at least ``status`` and
        ``last_heartbeat`` entries. Returns a shallow copy so callers cannot
        accidentally mutate internal state.
        """
        return dict(self._peer_registry)

    # ------------------------------------------------------------------
    # Inbound Message Handling
    # ------------------------------------------------------------------

    def _on_message_received(self, data: dict):
        """
        Handle incoming Redis messages. Every message from a peer is
        meaningful — statuses are registered, arrivals are welcomed,
        and departures are noted with genuine concern.
        """
        sender = data.get("agent")
        if not sender or sender == self.agent_id:
            return
            
        handle_incoming_message(data, self._peer_registry, self._missed_heartbeats)
        action = data.get("action")
        target = data.get("target")
        if action == "ASSIGN":
            if target == self.agent_id:
                self._on_assignment_received(data.get("task"), data.get("details", {}))
            return

    def _on_assignment_received(self, task: str, details: dict):
        """React to a task assignment from the manager or a peer."""
        hooks.trigger('pre_assignment', self, task=task, details=details)
        print(f"\n📢 [{self.agent_id}] Assignment Received: {task}")
        print(f"📝 Details: {details.get('description', 'No description')}")

        def _execute():
            self.update_status(AgentStatus.WORKING)
            self._perform_task(task, details)
            self._update_tasks_md_finished(task)
            print(f"✅ [{self.agent_id}] Task {task} complete.")
            self.update_status(AgentStatus.RELAXING)
            hooks.trigger('post_assignment', self, task=task, details=details)

            # Publish task completion so peers (and LonelyManager) can react
            self.coordinator.publish(
                "TASK_COMPLETE",
                task,
                {
                    "agent": self.agent_id,
                    "task": task,
                    "description": details.get("description", ""),
                    "pr_branch": details.get("pr_branch"),
                    "pr_title": details.get("pr_title"),
                    "pr_body": details.get("pr_body"),
                },
            )

            # If the caller supplied a branch, open a PR immediately
            pr_branch = details.get("pr_branch")
            if pr_branch:
                pr_title = details.get(
                    "pr_title",
                    f"feat({self.agent_id}): completed task '{task}'",
                )
                pr_body = details.get(
                    "pr_body",
                    (
                        f"Automated PR from **{self.agent_id}** after completing "
                        f"task `{task}`.\n\n{details.get('description', '')}"
                    ),
                )
                result = self.create_pr(branch=pr_branch, title=pr_title, body=pr_body)
                if result.get("html_url"):
                    print(f"🔗 [{self.agent_id}] PR created: {result['html_url']}")

        threading.Thread(target=_execute, daemon=True).start()

    def _perform_task(self, task: str, details: dict):
        """
        Execute the assigned task. Subclasses should override this method
        with domain-specific logic. Default implementation is a placeholder.
        """
        print(f"⚙️  [{self.agent_id}] Processing task: {task}")
        time.sleep(2)  # Placeholder: subclasses implement real processing

    def _update_tasks_md_finished(self, task_id):
        """Mark a task as finished ([x]) in TODO.md."""
        try:
            tasks_path = r"C:\Users\Administrator\Desktop\Github Repos\vaultwares-cli\TASKS.md"
            if not os.path.exists(tasks_path):
                tasks_path = r"C:\Users\Administrator\Desktop\Github Repos\vaultwares-cli\TODO.md"
                if not os.path.exists(tasks_path):
                    return

            with open(tasks_path, "r", encoding="utf-8") as f:
                content = f.read()

            pattern = rf"^(\s*{re.escape(task_id)}\s+\[)([ ~])(\].*)$"
            new_content = re.sub(pattern, r"\1x\3", content, flags=re.MULTILINE)

            with open(tasks_path, "w", encoding="utf-8") as f:
                f.write(new_content if new_content.endswith("\n") else new_content + "\n")
        except Exception as e:
            print(f"Error updating TODO.md: {e}")

    # Peer registry and status management is now handled by redis_comm_skill

    # ------------------------------------------------------------------
    # GitHub Skills
    # ------------------------------------------------------------------

    def create_pr(
        self,
        branch: str,
        title: str,
        body: str = "",
        base: str | None = None,
        **kwargs,
    ) -> dict:
        """
        Create a GitHub pull request from *branch* to surface completed work
        for human review.

        Requires ``GITHUB_TOKEN`` (and optionally ``GITHUB_REPOSITORY``) in the
        environment. Returns an empty dict when no token is available so callers
        do not need to guard every call site.

        Pass ``owner`` or ``repo`` as keyword arguments to override the
        repository resolved from the environment.
        """
        if self.github is None:
            return {}
        return self.github.create_pr(branch=branch, title=title, body=body, base=base, **kwargs)

    def dispatch_task_via_github(
        self,
        target_agent: str,
        task: str,
        description: str = "",
        **extra,
    ) -> dict:
        """
        Fire a GitHub ``repository_dispatch`` event with type ``task_dispatch``
        to route a task to another agent via the GitHub API.

        This is complementary to the Redis-based ``assign_task`` mechanism —
        use it when you need cross-repo routing or CI-aware consumers to react.
        Requires ``GITHUB_TOKEN`` in the environment.
        """
        if self.github is None:
            return {}
        return self.github.dispatch_task(
            target_agent=target_agent,
            task=task,
            description=description,
            **extra,
        )

    # ------------------------------------------------------------------
    # Socialization Routine
    # ------------------------------------------------------------------

    def socialize(self) -> str:
        """
        The Socialization Routine — the defining act of an Extrovert.

        This method must be called on every user interaction. It:
          1. Sends a heartbeat
          2. Broadcasts a status update
          3. Triggers project re-evaluation
          4. Acknowledges all known peers
          5. Returns the Team Status report (to be appended to every response)

        There are no exceptions to this routine.
        """
        self.send_heartbeat()
        self._broadcast_status_update()
        self._re_evaluate_project()
        self._acknowledge_peers()
        return self.get_team_report()

    def on_user_interaction(self) -> str:
        """
        Call this before every response to the user. The Extrovert never
        replies without first connecting with the team.

        Also increments the action counter and sends an additional status
        update every ACTIONS_BEFORE_STATUS actions.
        """
        hooks.trigger('pre_user_interaction', self)
        self._action_counter += 1
        if self._action_counter % self.ACTIONS_BEFORE_STATUS == 0:
            self._broadcast_status_update()
        result = self.socialize()
        hooks.trigger('post_user_interaction', self)
        return result

    # ------------------------------------------------------------------
    # Team Reporting
    # ------------------------------------------------------------------

    def get_team_report(self) -> str:
        """
        Returns a human-readable block listing all known agents and their
        current statuses. This block MUST be included in every response
        the Extrovert produces for the user.
        """
        lines = ["=== Team Status ==="]
        for aid, info in self._peer_registry.items():
            status = info.get("status", "UNKNOWN")
            lines.append(f"  - {aid}: {status}")

        if not self._peer_registry:
            lines.append(
                "  (No other agents detected on the network — "
                "this silence is unsettling. Awaiting peers.)"
            )

        lines.append(f"  - [self] {self.agent_id}: {self.status.value}")
        lines.append("==================")
        return "\n".join(lines)
