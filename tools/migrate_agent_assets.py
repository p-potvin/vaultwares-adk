"""
Migrate reusable agent assets into `vaultwares-adk` using an audit report.

This tool is intentionally cautious:
- Default is dry-run (prints intended actions)
- Requires explicit --write to modify files

Current supported migrations:
- Copy `SKILL.md` packages into `vaultwares-adk/imports/<repo>/<rel_path>`
- Replace original files with pointer stubs (optional)

More aggressive operations (deletions, submodule adds) are not performed by default.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence


DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    "target",
}


@dataclass(frozen=True)
class AuditItem:
    repo_root: str
    repo_name: str
    rel_path: str
    kind: str
    classification: str
    reason: str


def load_audit(path: Path) -> List[AuditItem]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items: List[AuditItem] = []
    for r in raw:
        items.append(
            AuditItem(
                repo_root=r["repo_root"],
                repo_name=r["repo_name"],
                rel_path=r["rel_path"],
                kind=r.get("kind", "other"),
                classification=r.get("classification", "manual-review"),
                reason=r.get("reason", ""),
            )
        )
    return items


def safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_pointer_stub(dst_file: Path, canonical_path: str) -> None:
    dst_file.write_text(
        "\n".join(
            [
                "# Moved",
                "",
                f"Canonical file: `{canonical_path}`",
                "",
            ]
        ),
        encoding="utf-8",
    )


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Migrate reusable agent assets into vaultwares-adk.")
    p.add_argument("--audit-json", required=True, help="Path to audit JSON produced by audit_agent_surfaces.py.")
    p.add_argument(
        "--adk-root",
        required=True,
        help="Path to the vaultwares-adk repo root (destination).",
    )
    p.add_argument(
        "--imports-dir",
        default="imports",
        help="Directory under ADK root to store imported assets (default: imports).",
    )
    p.add_argument(
        "--write",
        action="store_true",
        help="Perform writes. Without this flag the tool is dry-run.",
    )
    p.add_argument(
        "--replace-with-pointer",
        action="store_true",
        help="Replace migrated source files with pointer stubs (only when --write).",
    )
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    audit_path = Path(args.audit_json)
    agent_root = Path(args.agentciation_root)
    imports_root = agent_root / args.imports_dir

    items = load_audit(audit_path)

    planned: List[str] = []
    copied = 0
    pointed = 0

    for it in items:
        if it.classification not in {"move-to-ADK"}:
            continue
        src_repo = Path(it.repo_root)
        if src_repo.resolve() == agent_root.resolve():
            # Never "migrate" assets from the canonical repo into itself.
            continue
        src_path = src_repo / Path(it.rel_path)
        if not src_path.exists():
            continue

        # Only migrate SKILL.md and *.agent.md in this first pass; other files require manual review.
        if src_path.name not in {"SKILL.md"} and not src_path.name.endswith(".agent.md"):
            continue

        dst_path = imports_root / it.repo_name / Path(it.rel_path)
        planned.append(f"COPY {src_path} -> {dst_path}")

        if args.write:
            safe_mkdir(dst_path.parent)
            dst_path.write_bytes(src_path.read_bytes())
            copied += 1

            if args.replace_with_pointer:
                canonical = str(Path(args.imports_dir) / it.repo_name / Path(it.rel_path)).replace("\\", "/")
                write_pointer_stub(src_path, canonical)
                pointed += 1

    for line in planned:
        print(line)

    if args.write:
        print(f"Copied: {copied}")
        if args.replace_with_pointer:
            print(f"Pointers written: {pointed}")
    else:
        print(f"Planned copies: {len(planned)} (dry-run)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
