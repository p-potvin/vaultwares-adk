import subprocess
import os

def record_agent_change(project, kind, summary, commands, files, plan_path=None, actor=None, agent_role=None, model=None, thinking=None, mode=None, permissions=None, network=None, tools_used=None, mcp_servers_accessed=None, workspace_root=None):
    """
    Calls the VaultWares agent-ledger PowerShell script to record an agent change.
    All arguments except project, kind, summary, commands, and files are optional.
    """
    script_path = os.path.expandvars(r"C:\Users\Administrator\Desktop\Github Repos\agent-ledger\scripts\record-agent-change.ps1")
    cmd = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", script_path,
        f"-Project", project,
        f"-Kind", kind,
        f"-Summary", summary,
        f"-Commands", f"@({', '.join([repr(c) for c in commands])})",
        f"-Files", f"@({', '.join([repr(f) for f in files])})"
    ]
    if plan_path:
        cmd += ["-PlanPath", plan_path]
    if actor:
        cmd += ["-Actor", actor]
    if agent_role:
        cmd += ["-AgentRole", agent_role]
    if model:
        cmd += ["-Model", model]
    if thinking:
        cmd += ["-Thinking", thinking]
    if mode:
        cmd += ["-Mode", mode]
    if permissions:
        cmd += ["-Permissions", permissions]
    if network:
        cmd += ["-Network", network]
    if tools_used:
        cmd += ["-ToolsUsed", f"@({', '.join([repr(t) for t in tools_used])})"]
    if mcp_servers_accessed:
        cmd += ["-McpServersAccessed", f"@({', '.join([repr(m) for m in mcp_servers_accessed])})"]
    if workspace_root:
        cmd += ["-WorkspaceRoot", workspace_root]
    subprocess.run(cmd, check=True)
