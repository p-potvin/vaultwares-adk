"""
Sync a canonical managed block from `vaultwares-agentciation` into consumer repos.

This script focuses on pointer + managed-block synchronization rather than deep merges.
It supports:
- --check: report drift without modifying files
- --write: apply updates

Targets (initial):
- CLAUDE.md
- .github/copilot-instructions.md
- .windsurfrules
- .cursor/rules/*.mdc (by default: vault-designer.mdc)

Canonical source:
- `skills/vault-designer/SKILL.md` is treated as the primary instruction surface.
"""

from __future__ import annotations

import argparse
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_EXCLUDE_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    "target",
}

MANAGED_START = "<!-- VAULTWARES_AGENTCIATION:MANAGED:START -->"
MANAGED_END = "<!-- VAULTWARES_AGENTCIATION:MANAGED:END -->"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def extract_managed_block(canonical_text: str) -> str:
    lines = canonical_text.splitlines()
    snippet = "\n".join(lines).rstrip() + "\n"
    return "\n".join([MANAGED_START, snippet, MANAGED_END]) + "\n"


def upsert_managed_block(existing: str, managed_block: str) -> Tuple[str, bool]:
    if MANAGED_START in existing and MANAGED_END in existing:
        pre, rest = existing.split(MANAGED_START, 1)
        _old, post = rest.split(MANAGED_END, 1)
        new_text = pre.rstrip() + "\n\n" + managed_block + post.lstrip()
        return (new_text, new_text != existing)
    # Append at end.
    new_text = existing.rstrip() + "\n\n" + managed_block
    return (new_text + ("\n" if not new_text.endswith("\n") else ""), True)


def discover_repos(roots: Sequence[Path]) -> List[Path]:
    repos: List[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for dirpath, dirnames, _filenames in os.walk(root):
            p = Path(dirpath)
            dirnames[:] = [d for d in dirnames if d not in DEFAULT_EXCLUDE_DIR_NAMES]
            if (p / ".git").exists():
                rp = str(p.resolve())
                if rp not in seen:
                    repos.append(p)
                    seen.add(rp)
                dirnames[:] = []
    return sorted(repos, key=lambda x: str(x).lower())


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sync vaultwares-agentciation managed blocks into consumer repos.")
    p.add_argument(
        "--agentciation-root",
        required=True,
        help="Path to the vaultwares-agentciation repo root (canonical source).",
    )
    p.add_argument(
        "--roots",
        nargs="*",
        default=[],
        help="Workspace roots to scan for repos (defaults to common local roots).",
    )
    p.add_argument("--check", action="store_true", help="Report drift only; do not write.")
    p.add_argument("--write", action="store_true", help="Apply updates.")
    p.add_argument(
        "--sync-github-agents-snapshot",
        action="store_true",
        help="Sync `.github/agents` from `skills/mirrors/<repo>/.github/agents` when present.",
    )
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.check and args.write:
        raise SystemExit("Choose only one: --check or --write")

    agent_root = Path(args.agentciation_root)
    canonical_path = agent_root / "skills" / "vault-designer" / "SKILL.md"
    canonical_text = read_text(canonical_path)
    managed_block = extract_managed_block(canonical_text)

    if args.roots:
        roots = [Path(r) for r in args.roots]
    else:
        candidates = [
            Path(r"C:\Users\Administrator\Desktop\Github Repos"),
            Path(r"C:\Users\Administrator\Desktop\business"),
        ]
        roots = [c for c in candidates if c.exists()]
        if not roots:
            roots = [Path.cwd()]

    repos = discover_repos(roots)

    targets = [
        ("CLAUDE.md", "CLAUDE.md"),
        (".github/copilot-instructions.md", ".github/copilot-instructions.md"),
        (".windsurfrules", ".windsurfrules"),
        (".cursor/rules/vault-designer.mdc", ".cursor/rules/vault-designer.mdc"),
    ]

    changed_count = 0
    checked_count = 0
    snapshot_updates = 0

    for repo in repos:
        # Skip the canonical repo itself.
        if repo.resolve() == agent_root.resolve():
            continue

        for rel_src, rel_dst in targets:
            dst = repo / rel_dst
            if not dst.exists():
                continue

            existing = read_text(dst)
            updated, changed = upsert_managed_block(existing, managed_block)
            checked_count += 1

            if changed:
                print(f"DRIFT {repo.name}: {rel_dst}")
                if args.write:
                    write_text(dst, updated)
                    changed_count += 1

        if args.sync_github_agents_snapshot:
            canonical_snapshot = agent_root / "skills" / "mirrors" / repo.name / ".github" / "agents"
            dst_snapshot = repo / ".github" / "agents"
            if canonical_snapshot.exists():
                drift = False
                if not dst_snapshot.exists():
                    drift = True
                else:
                    # Shallow drift check: compare relative file lists and sizes.
                    src_files = sorted([p.relative_to(canonical_snapshot).as_posix() for p in canonical_snapshot.rglob("*") if p.is_file()])
                    dst_files = sorted([p.relative_to(dst_snapshot).as_posix() for p in dst_snapshot.rglob("*") if p.is_file()])
                    if src_files != dst_files:
                        drift = True
                    else:
                        for rel in src_files:
                            sp = canonical_snapshot / rel
                            dp = dst_snapshot / rel
                            if not dp.exists() or sp.stat().st_size != dp.stat().st_size:
                                drift = True
                                break

                if drift:
                    print(f"DRIFT {repo.name}: .github/agents (snapshot)")
                    if args.write:
                        if dst_snapshot.exists():
                            for child in dst_snapshot.iterdir():
                                if child.is_dir():
                                    shutil.rmtree(child)
                                else:
                                    child.unlink()
                        else:
                            dst_snapshot.mkdir(parents=True, exist_ok=True)
                        # Copy snapshot content into destination.
                        for src_item in canonical_snapshot.rglob("*"):
                            rel = src_item.relative_to(canonical_snapshot)
                            dst_item = dst_snapshot / rel
                            if src_item.is_dir():
                                dst_item.mkdir(parents=True, exist_ok=True)
                            else:
                                dst_item.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(src_item, dst_item)
                        snapshot_updates += 1

    if args.write:
        print(f"Updated files: {changed_count}")
        if args.sync_github_agents_snapshot:
            print(f"Updated snapshots: {snapshot_updates}")
    else:
        print(f"Checked files: {checked_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
