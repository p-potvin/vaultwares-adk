"""
Audit agent-related instruction/skill/tool surfaces across a workspace.

Goal:
- Identify files that are likely reusable (cross-project) vs project-specific
- Produce a report that can drive a safe migration into `vaultwares-agentciation`

This script is intentionally conservative:
- Defaults to dry reporting (no changes)
- Avoids scanning common generated/vendor directories
- Avoids scanning inside nested git repos (submodules) when walking a repo
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


DEFAULT_EXCLUDE_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".next",
    ".cache",
    "dist",
    "build",
    "out",
    "target",
    "obj",
    "bin",
}

AGENT_SURFACE_PATH_PREFIXES = (
    ".github/agents",
    ".codex",
    ".agents",
    ".claude",
    ".cursor/rules",
    ".vscode",
)

AGENT_SURFACE_FILENAMES = {
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "skills.md",
    "AGENT_MANIFEST.md",
    ".windsurfrules",
}

AGENT_SURFACE_GLOBS = (
    ".github/copilot-instructions.md",
    "**/SKILL.md",
    "**/*.agent.md",
)


@dataclass(frozen=True)
class Finding:
    repo_root: str
    repo_name: str
    rel_path: str
    kind: str  # instruction|skill|tooling|ide-config|other
    classification: str  # keep-local-project-specific|move-to-agentciation|replace-with-pointer|manual-review
    reason: str


def _is_git_repo_root(path: Path) -> bool:
    git_marker = path / ".git"
    return git_marker.is_dir() or git_marker.is_file()


def _walk_repo_files(repo_root: Path, exclude_dir_names: set[str]) -> Iterable[Path]:
    """
    Walk repo files without descending into nested git repos (submodules),
    and skipping common generated/vendor directories.
    """
    for dirpath, dirnames, filenames in os.walk(repo_root):
        p = Path(dirpath)

        # Never descend into excluded directories.
        dirnames[:] = [d for d in dirnames if d not in exclude_dir_names]

        # Avoid scanning inside nested repos (submodules) when walking a parent repo.
        # If the current directory (not the root) is a git repo, do not descend further.
        if p != repo_root and _is_git_repo_root(p):
            dirnames[:] = []
            continue

        for name in filenames:
            yield p / name


def _classify(path_rel_posix: str) -> Tuple[str, str, str]:
    """
    Returns: (kind, classification, reason)
    """
    rel_lower = path_rel_posix.lower()
    base = Path(path_rel_posix).name

    # Skills are typically reusable; but may be project-specific if under app code.
    if base == "SKILL.md":
        return ("skill", "move-to-agentciation", "Skill package detected (SKILL.md).")

    if base.endswith(".agent.md"):
        return ("instruction", "move-to-agentciation", "Agent definition file detected (*.agent.md).")

    if base in AGENT_SURFACE_FILENAMES:
        # AGENTS.md is ambiguous: usually project-specific.
        if base == "AGENTS.md":
            return ("instruction", "manual-review", "AGENTS.md is usually project-specific; review before moving.")
        if base in {"CLAUDE.md", "GEMINI.md", "AGENT_MANIFEST.md", "skills.md"}:
            return ("instruction", "replace-with-pointer", "Agent instruction surface detected; prefer central source + pointer.")
        if base == ".windsurfrules":
            return ("ide-config", "replace-with-pointer", "IDE/agent rules file detected; prefer central managed source + pointer.")

    # Copilot instructions are often reusable, but sometimes project-specific.
    if rel_lower.endswith(".github/copilot-instructions.md"):
        return ("instruction", "replace-with-pointer", "Copilot instructions surface detected; prefer central managed source + pointer.")

    # Known agent surface folders.
    for prefix in AGENT_SURFACE_PATH_PREFIXES:
        if rel_lower.startswith(prefix + "/") or rel_lower == prefix:
            # `.vscode` is often project-specific config; keep local unless it's explicitly agent-related.
            if prefix == ".vscode":
                return ("ide-config", "manual-review", "VS Code config detected; review before moving.")
            return ("instruction", "manual-review", f"Agent surface directory detected under `{prefix}`; review for reuse.")

    return ("other", "ignore", "Not recognized as an agent surface.")


def discover_repos(roots: Sequence[Path], exclude_dir_names: set[str]) -> List[Path]:
    repos: List[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for dirpath, dirnames, _filenames in os.walk(root):
            p = Path(dirpath)
            dirnames[:] = [d for d in dirnames if d not in exclude_dir_names]

            if _is_git_repo_root(p):
                rp = str(p.resolve())
                if rp not in seen:
                    repos.append(p)
                    seen.add(rp)
                # Do not descend further; nested repos will be discovered by their own `.git`.
                dirnames[:] = []
    return sorted(repos, key=lambda x: str(x).lower())


def audit_repo(repo_root: Path, exclude_dir_names: set[str]) -> List[Finding]:
    findings: List[Finding] = []
    repo_name = repo_root.name

    for file_path in _walk_repo_files(repo_root, exclude_dir_names):
        try:
            rel = file_path.relative_to(repo_root).as_posix()
        except ValueError:
            continue

        # Fast prefilter: avoid classifying everything.
        base = file_path.name
        rel_lower = rel.lower()
        if (
            base not in AGENT_SURFACE_FILENAMES
            and base != "SKILL.md"
            and not base.endswith(".agent.md")
            and not rel_lower.endswith(".github/copilot-instructions.md")
            and not any(rel_lower.startswith(p + "/") for p in AGENT_SURFACE_PATH_PREFIXES)
        ):
            continue

        kind, classification, reason = _classify(rel)
        if classification == "ignore":
            continue

        findings.append(
            Finding(
                repo_root=str(repo_root.resolve()),
                repo_name=repo_name,
                rel_path=rel,
                kind=kind,
                classification=classification,
                reason=reason,
            )
        )
    return findings


def write_markdown(out_path: Path, findings: Sequence[Finding]) -> None:
    by_repo: dict[str, List[Finding]] = {}
    for f in findings:
        by_repo.setdefault(f.repo_name, []).append(f)

    lines: List[str] = []
    lines.append("# Agent Surface Audit")
    lines.append("")
    lines.append("This report lists agent-related instruction/skill/tool surfaces found across repos.")
    lines.append("Classifications are conservative: many items are marked `manual-review`.")
    lines.append("")

    for repo_name in sorted(by_repo.keys(), key=lambda x: x.lower()):
        lines.append(f"## {repo_name}")
        lines.append("")
        for f in sorted(by_repo[repo_name], key=lambda x: x.rel_path.lower()):
            lines.append(f"- `{f.rel_path}` — `{f.classification}` ({f.kind}): {f.reason}")
        lines.append("")

    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Audit agent-related surfaces across repos.")
    p.add_argument(
        "--roots",
        nargs="*",
        default=[],
        help="Root directories to scan (defaults to common local workspace roots if present).",
    )
    p.add_argument(
        "--out-json",
        default="agent-surface-audit.json",
        help="Output JSON path (default: agent-surface-audit.json in CWD).",
    )
    p.add_argument(
        "--out-md",
        default="agent-surface-audit.md",
        help="Output Markdown path (default: agent-surface-audit.md in CWD).",
    )
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    roots: List[Path] = []
    if args.roots:
        roots = [Path(r) for r in args.roots]
    else:
        env_roots = os.getenv("AGENT_AUDIT_ROOTS")
        if env_roots:
            # Supports comma-separated list of roots in environment variable
            roots = [Path(r.strip()) for r in env_roots.split(",") if r.strip()]

    if not roots:
        roots = [Path.cwd()]

    exclude_dir_names = set(DEFAULT_EXCLUDE_DIR_NAMES)

    repos = discover_repos(roots, exclude_dir_names)
    all_findings: List[Finding] = []
    for repo_root in repos:
        all_findings.extend(audit_repo(repo_root, exclude_dir_names))

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)

    out_json.write_text(
        json.dumps([asdict(f) for f in all_findings], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_markdown(out_md, all_findings)

    print(f"Repos scanned: {len(repos)}")
    print(f"Findings: {len(all_findings)}")
    print(f"Wrote: {out_json.resolve()}")
    print(f"Wrote: {out_md.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

