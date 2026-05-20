"""
Columbo — Codebase Forensics & Recipe Extraction Agent

Distills codebases into portable natural-language "recipes" that any
AI Assistant can use to rebuild the product from scratch. Monolithic
architecture with human-in-the-loop checkpoints.

Usage:
    python columbo.py /path/to/codebase --output ./recipe
"""

import json
import os
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from vaultwares_adk import ExtrovertAgent, AgentStatus


class AuditTier(Enum):
    ESSENTIAL = "essential"
    GAME_CHANGER = "game_changer"
    GREAT = "great"
    CAREFUL = "careful"
    USELESS = "useless"


# Directories to always skip when walking source trees
SKIP_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".cache", ".tox", "egg-info",
})

# Extensions that count as "source code"
SOURCE_EXTENSIONS = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".scss",
    ".html", ".vue", ".svelte", ".go", ".rs", ".java", ".kt",
    ".rb", ".php", ".cs", ".cpp", ".c", ".h", ".swift",
})


class ColumboAgent(ExtrovertAgent):
    """
    Codebase Forensics & Recipe Extraction Agent.

    Named after the TV detective — seemingly bumbling, actually razor-sharp.
    Operates in extract mode (code-as-truth) with HITL checkpoints at
    audit, gap-map, compose, and handoff.
    """

    AGENT_TYPE = "forensics"
    SKILLS = [
        "codebase_audit",
        "intent_extraction",
        "ux_flow_mapping",
        "domain_modeling",
        "gap_analysis",
        "anchored_interview",
        "recipe_composition",
        "round_trip_verification",
    ]

    def __init__(
        self,
        agent_id: str = "columbo",
        channel: str = "tasks",
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        recipe_output_dir: str = "./recipe",
    ):
        super().__init__(agent_id, channel, redis_host, redis_port, redis_db)
        self.recipe_output_dir = Path(recipe_output_dir)
        self.target_path: Optional[Path] = None
        self.audit_result: dict = {}
        self.blind_spec: dict = {}
        self.sighted_spec: dict = {}
        self.contradictions: list = []
        self.gap_queue: list = []
        self.interview_transcript: list = []
        self.recipe: dict = {}
        self.confidence: float = 0.0

    # ------------------------------------------------------------------
    # Task Dispatcher
    # ------------------------------------------------------------------

    def _perform_task(self, task: str, details: dict):
        """Route lifecycle phases through the Columbo pipeline."""
        print(f"\U0001f50d [{self.agent_id}] Received task: {task}")

        handlers = {
            "extract": self._run_full_extraction,
            "audit": self._audit_inputs,
            "blind_pass": self._blind_pass,
            "sighted_pass": self._sighted_pass,
            "gap_map": self._gap_map,
            "interview": self._interview,
            "compose": self._compose_recipe,
            "verify": self._round_trip_verify,
            "handoff": self._run_handoff,
            # HITL resume handlers — called by operator after approval
            "resume_gap_interview": self._run_gap_and_interview,
            "resume_compose": self._run_compose_and_verify,
            "resume_handoff": self._run_handoff,
        }

        handler = handlers.get(task)
        if handler:
            handler(details)
        else:
            print(f"[{self.agent_id}] Unknown task: {task}. Making a note...")
            self._log_unknown_task(task, details)

    # ------------------------------------------------------------------
    # Full Extraction Pipeline
    # ------------------------------------------------------------------

    def _request_hitl_approval(self, checkpoint: str, context: dict) -> None:
        """
        Pause the pipeline and emit an 'awaiting_approval' status for the
        given checkpoint.  The pipeline does NOT auto-continue — the operator
        must send a fresh task to resume (e.g. task='resume_gap_interview',
        task='resume_compose', or task='resume_handoff').
        """
        payload = {
            "status": "awaiting_approval",
            "checkpoint": checkpoint,
            "target_path": str(self.target_path),
            "recipe_output_dir": str(self.recipe_output_dir),
            **context,
        }
        print(f"[{self.agent_id}] ⏸  HITL checkpoint: {checkpoint}. Awaiting operator approval.")
        self._publish_result("hitl", json.dumps(payload, default=str))

    def _run_full_extraction(self, details: dict):
        """Run the complete Columbo extraction pipeline."""
        self.target_path = Path(details.get("target", "."))
        acceptance = details.get("acceptance", {})

        print(f"[{self.agent_id}] *adjusts trenchcoat* Let me see what we have here...")
        print(f"   Target: {self.target_path}")

        # Phase 1: Audit
        self._audit_inputs({"target": str(self.target_path), **acceptance})
        if not self.audit_result.get("proceed", False):
            print(f"[{self.agent_id}] Missing essentials. Pivoting gracefully.")
            self._publish_result("extract", json.dumps({
                "status": "refused",
                "reason": "essentials_missing",
                "missing": self.audit_result.get("missing", []),
                "recommendation": self.audit_result.get("recommendation", ""),
            }))
            return

        # Phase 2: Blind pass
        self._blind_pass({"target": str(self.target_path)})

        # Phase 3: Sighted pass
        self._sighted_pass({"target": str(self.target_path)})

        # HITL gate 1 — operator reviews contradictions before gap mapping
        self._request_hitl_approval("post_sighted_pass", {
            "contradictions": len(self.contradictions),
            "message": "Review sighted-pass contradictions, then approve to continue to gap map + interview.",
        })
        return

    def _run_gap_and_interview(self, details: dict):
        """Resume pipeline from gap-map phase (called after HITL approval).

        Args:
            details: Reserved for future operator-supplied context; unused.
        """
        # Phase 4: Gap map
        self._gap_map({})

        # Phase 5: Interview (conditional on gaps)
        if self.gap_queue:
            self._interview({"gaps": self.gap_queue})

        # HITL gate 2 — operator reviews gap map / interview before recipe composition
        self._request_hitl_approval("post_gap_interview", {
            "gaps": len(self.gap_queue),
            "message": "Review gap map and interview transcript, then approve to compose recipe.",
        })

    def _run_compose_and_verify(self, details: dict):
        """Resume pipeline from compose phase (called after HITL approval).

        Args:
            details: Reserved for future operator-supplied context; unused.
        """
        # Phase 6: Compose
        self._compose_recipe({"output_dir": str(self.recipe_output_dir)})

        # Phase 7: Round-trip verification
        self._round_trip_verify({})

        # HITL gate 3 — operator reviews composed recipe before handoff
        self._request_hitl_approval("pre_handoff", {
            "recipe": self.recipe,
            "message": "Review composed recipe, then approve to finalize handoff.",
        })

    def _run_handoff(self, details: dict):
        """Finalize handoff (called after final HITL approval).

        Args:
            details: Reserved for future operator-supplied context; unused.
        """
        # Phase 8: Handoff
        self._handoff({})

    # ------------------------------------------------------------------
    # Phase 1: Audit
    # ------------------------------------------------------------------

    def _audit_inputs(self, details: dict):
        """
        Classify inputs against the 5-tier taxonomy.
        HITL checkpoint: pauses for human review of classifications.
        """
        target = Path(details.get("target", self.target_path or "."))
        print(f"[{self.agent_id}] *squints at notepad* Classifying inputs...")

        classified = {t.value: [] for t in AuditTier}
        missing_essentials = []

        # --- Essentials ---
        has_source = self._has_source_code(target)
        if has_source:
            classified["essential"].append("source_code")
        else:
            missing_essentials.append("source_code")

        # --- Game changers ---
        if (target / ".git").exists():
            classified["game_changer"].append("git_history")

        if self._has_tests(target):
            classified["game_changer"].append("test_suite")

        ci_markers = [target / ".github", target / ".gitlab-ci.yml", target / "Jenkinsfile"]
        if any(p.exists() for p in ci_markers):
            classified["game_changer"].append("ci_cd_config")

        if (target / "assets").exists() or (target / "brand").exists():
            classified["game_changer"].append("design_assets")

        # --- Great ---
        if (target / "README.md").exists():
            classified["great"].append("readme")
        if (target / "docs").exists():
            classified["great"].append("docs_directory")

        for manifest in ["package.json", "pyproject.toml", "requirements.txt",
                         "Cargo.toml", "go.mod", "pom.xml"]:
            if (target / manifest).exists():
                classified["great"].append(f"manifest:{manifest}")

        # --- Confidence + proceed ---
        proceed = len(missing_essentials) == 0
        self.confidence = self._calculate_confidence(classified)

        self.audit_result = {
            "classified": classified,
            "missing": missing_essentials,
            "proceed": proceed,
            "confidence": self.confidence,
            "recommendation": self._audit_recommendation(classified, missing_essentials),
        }

        print(f"[{self.agent_id}] Audit complete. Confidence: {self.confidence:.0%}")
        for tier, items in classified.items():
            if items:
                print(f"   {tier}: {', '.join(items)}")
        if missing_essentials:
            print(f"   MISSING ESSENTIALS: {', '.join(missing_essentials)}")

        print(f"[{self.agent_id}] HITL: Review classifications before continuing.")
        self._publish_result("audit", json.dumps(self.audit_result))

    # ------------------------------------------------------------------
    # Phase 2: Blind Pass
    # ------------------------------------------------------------------

    def _blind_pass(self, details: dict):
        """Extract intent and behavior WITHOUT reading source code."""
        target = Path(details.get("target", self.target_path or "."))
        print(f"[{self.agent_id}] Blind pass — getting the lay of the land...")

        spec = {
            "intent": "",
            "ux_flows": [],
            "behavioral_expectations": [],
            "domain_concepts": [],
            "non_code_signals": [],
        }

        # README as intent signal
        readme_path = target / "README.md"
        if readme_path.exists():
            content = readme_path.read_text(encoding="utf-8", errors="replace")
            spec["non_code_signals"].append({
                "source": "README.md", "type": "documentation",
                "content_summary": content[:3000],
            })

        # Test names reveal behavior without reading implementation
        test_files = list(target.rglob("test_*.py")) + list(target.rglob("*_test.py"))
        test_files += list(target.rglob("*.test.ts")) + list(target.rglob("*.test.js"))
        test_files = [f for f in test_files if not any(s in f.parts for s in SKIP_DIRS)]
        spec["behavioral_expectations"] = [f.stem for f in test_files[:30]]

        # Directory structure = architecture signal
        top_dirs = sorted(
            d.name for d in target.iterdir()
            if d.is_dir() and not d.name.startswith(".") and d.name not in SKIP_DIRS
        )
        spec["domain_concepts"] = top_dirs

        self.blind_spec = spec
        print(f"[{self.agent_id}] Blind pass done. "
              f"{len(spec['non_code_signals'])} signals, "
              f"{len(spec['behavioral_expectations'])} behavioral hints, "
              f"{len(spec['domain_concepts'])} domain concepts.")
        self._publish_result("blind_pass", json.dumps(spec, default=str))

    # ------------------------------------------------------------------
    # Phase 3: Sighted Pass
    # ------------------------------------------------------------------

    def _sighted_pass(self, details: dict):
        """Open code, validate against blind pass, flag contradictions."""
        target = Path(details.get("target", self.target_path or "."))
        print(f"[{self.agent_id}] *opens file* Now let me look at the code...")

        spec = {
            "file_manifest": [],
            "stack_assessment": {},
            "contradictions": [],
            "embedded_literals": [],
        }

        # Walk source tree
        source_files = [
            f for f in target.rglob("*")
            if f.is_file()
            and f.suffix in SOURCE_EXTENSIONS
            and not any(s in f.parts for s in SKIP_DIRS)
        ]

        spec["file_manifest"] = [
            {"path": str(f.relative_to(target)), "size": f.stat().st_size}
            for f in source_files[:300]
        ]

        # Assess stack (fresh, not transcribed)
        ext_counts = {}
        for f in source_files:
            ext_counts[f.suffix] = ext_counts.get(f.suffix, 0) + 1
        spec["stack_assessment"] = {
            "detected_extensions": ext_counts,
            "primary_language": max(ext_counts, key=ext_counts.get) if ext_counts else "unknown",
            "note": "Assessed fresh. Original stack is a hint, not a constraint.",
        }

        # Flag contradictions between blind and sighted
        blind_dirs = set(self.blind_spec.get("domain_concepts", []))
        code_dirs = {f.parent.name for f in source_files} - SKIP_DIRS
        unexpected = code_dirs - blind_dirs - {""}
        if unexpected:
            spec["contradictions"].append({
                "type": "unexpected_code_locations",
                "details": f"Code in directories invisible from blind pass: {unexpected}",
            })

        self.sighted_spec = spec
        self.contradictions = spec["contradictions"]
        print(f"[{self.agent_id}] Sighted pass done. "
              f"{len(source_files)} files, {len(spec['contradictions'])} contradictions.")
        self._publish_result("sighted_pass", json.dumps(spec, default=str))

    # ------------------------------------------------------------------
    # Phase 4: Gap Map
    # ------------------------------------------------------------------

    def _gap_map(self, details: dict):
        """
        Build the interview queue from ambiguities and missing rationale.
        HITL checkpoint: human reviews gaps before interview begins.
        """
        print(f"[{self.agent_id}] Mapping what I still don't know...")
        gaps = []

        for c in self.contradictions:
            gaps.append({
                "type": "contradiction", "priority": "high",
                "source": c,
                "question": f"I noticed {c.get('type', 'something unusual')}. Walk me through why?",
                "expected_answer": "code_version",
            })

        game_changers = self.audit_result.get("classified", {}).get("game_changer", [])
        if "test_suite" not in game_changers:
            gaps.append({
                "type": "missing_acceptance", "priority": "critical",
                "question": "How do you know this product works? What breaks if it doesn't?",
                "expected_answer": None,
            })

        if "design_assets" not in game_changers:
            gaps.append({
                "type": "missing_visual_ground_truth", "priority": "high",
                "question": "What should this look like? Walk me through the main screens.",
                "expected_answer": None,
            })

        gaps.append({
            "type": "intent_verification", "priority": "critical",
            "question": "In one sentence, what does this product do for its users?",
            "expected_answer": self.blind_spec.get("intent"),
        })

        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        self.gap_queue = sorted(gaps, key=lambda g: priority_order.get(g["priority"], 4))

        print(f"[{self.agent_id}] {len(gaps)} gaps identified.")
        for g in self.gap_queue:
            print(f"   [{g['priority']}] {g['type']}")

        print(f"[{self.agent_id}] HITL: Review gap list before interview begins.")
        self._publish_result("gap_map", json.dumps(self.gap_queue, default=str))

    # ------------------------------------------------------------------
    # Phase 5: Interview
    # ------------------------------------------------------------------

    def _interview(self, details: dict):
        """
        Columbo-style anchored contradiction interview.
        HITL: All questions visible; operator can override/skip/redirect.
        """
        gaps = details.get("gaps", self.gap_queue)
        print(f"[{self.agent_id}] Just a few questions...")

        transcript = []
        for i, gap in enumerate(gaps):
            entry = {
                "question_number": i + 1,
                "gap_type": gap["type"],
                "priority": gap["priority"],
                "question": gap["question"],
                "expected_from_code": gap.get("expected_answer"),
                "client_response": None,
                "divergence_detected": False,
                "notes": "",
            }
            print(f"   Q{i+1}/{len(gaps)} [{gap['priority']}]: {gap['question']}")
            print("   HITL: Awaiting response...")
            transcript.append(entry)

        self.interview_transcript = transcript
        print(f"[{self.agent_id}] Interview complete. {len(transcript)} questions asked.")
        self._publish_result("interview", json.dumps(transcript, default=str))

    # ------------------------------------------------------------------
    # Phase 6: Compose
    # ------------------------------------------------------------------

    def _compose_recipe(self, details: dict):
        """
        Write the recipe project.
        HITL checkpoint: human reviews recipe before finalization.
        """
        output_dir = Path(details.get("output_dir", self.recipe_output_dir))
        print(f"[{self.agent_id}] Time to write the recipe...")

        # Scaffold directories
        for subdir in ["ux", "domain", "assets", "tests"]:
            (output_dir / subdir).mkdir(parents=True, exist_ok=True)

        # intent.md
        (output_dir / "intent.md").write_text(
            self._render_intent(), encoding="utf-8"
        )
        # port.yaml
        (output_dir / "port.yaml").write_text(
            self._render_port_yaml(), encoding="utf-8"
        )
        # interview.md — always written (empty placeholder when no interview conducted)
        (output_dir / "interview.md").write_text(
            self._render_interview(), encoding="utf-8"
        )
        # revisions.md
        (output_dir / "revisions.md").write_text(
            self._render_revisions(), encoding="utf-8"
        )

        written = ["intent.md", "port.yaml", "interview.md", "revisions.md"]

        self.recipe = {"output_dir": str(output_dir), "files_written": written}
        print(f"[{self.agent_id}] Recipe composed: {', '.join(written)}")
        print(f"[{self.agent_id}] HITL: Review recipe before finalization.")
        self._publish_result("compose", json.dumps(self.recipe, default=str))

    # ------------------------------------------------------------------
    # Phase 7: Verify
    # ------------------------------------------------------------------

    def _round_trip_verify(self, details: dict):
        """Request a rebuild from the recipe and diff behavior (v1 placeholder)."""
        print(f"[{self.agent_id}] Round-trip verification (placeholder in v1).")
        print(f"   Recipe at: {self.recipe_output_dir}")
        print(f"   Original at: {self.target_path}")
        self._publish_result("verify", json.dumps({
            "status": "v1_placeholder",
            "confidence": self.confidence,
        }))

    # ------------------------------------------------------------------
    # Phase 8: Handoff
    # ------------------------------------------------------------------

    def _handoff(self, details: dict):
        """Emit the portable product package."""
        print(f"[{self.agent_id}] Here's your recipe, sir.")
        print(f"   Output: {self.recipe_output_dir}")
        print(f"   Confidence: {self.confidence:.0%}")

        report = {
            "status": "complete",
            "recipe_path": str(self.recipe_output_dir),
            "confidence": self.confidence,
            "contradictions_remaining": len(self.contradictions),
            "gaps_remaining": len(self.gap_queue),
        }
        print(f"[{self.agent_id}] Oh, and one more thing... "
              "you might want production telemetry for the next pass.")
        self._publish_result("handoff", json.dumps(report))

    # ------------------------------------------------------------------
    # Recipe Renderers
    # ------------------------------------------------------------------

    def _render_intent(self) -> str:
        blind_concepts = ", ".join(self.blind_spec.get("domain_concepts", [])[:10])
        stack = self.sighted_spec.get("stack_assessment", {})
        return "\n".join([
            "# Intent",
            "",
            f"*Extracted by Columbo from `{self.target_path}`*",
            "",
            "## What is this product?",
            "",
            "> Synthesize from blind pass + interview.",
            "",
            "## Who is it for?",
            "",
            "> Extract from UX flows and behavioral signals.",
            "",
            "## Domain Concepts (from structure)",
            "",
            f"{blind_concepts}",
            "",
            "## Stack Assessment (fresh)",
            "",
            f"- Primary language: {stack.get('primary_language', 'unknown')}",
            f"- Extensions: {json.dumps(stack.get('detected_extensions', {}))}",
            "",
            "## Key Decisions",
            "",
            "> Extract from git history + contradiction analysis.",
            "",
            "---",
            f"*Confidence: {self.confidence:.0%} | "
            f"Contradictions: {len(self.contradictions)} | "
            f"Columbo v0.1.0*",
        ])

    def _render_port_yaml(self) -> str:
        stack = self.sighted_spec.get("stack_assessment", {})
        return "\n".join([
            "# port.yaml",
            f"# Source: {self.target_path}",
            "",
            "version: '0.1.0'",
            "generator: columbo",
            f"confidence: {self.confidence}",
            "",
            "stack:",
            f"  primary_language: {stack.get('primary_language', 'unknown')}",
            f"  detected_extensions: {json.dumps(stack.get('detected_extensions', {}))}",
            "  recommendation: Assess based on intent, not original implementation.",
            "",
            "pinned: []",
            "",
            f"gaps: {len(self.gap_queue)}",
            f"contradictions: {len(self.contradictions)}",
            "",
            "contents:",
            "  - intent.md",
            "  - ux/",
            "  - domain/",
            "  - assets/",
            "  - tests/",
            "  - interview.md",
            "  - revisions.md",
        ])

    def _render_interview(self) -> str:
        lines = [
            "# Interview Transcript",
            "",
            f"*Columbo on `{self.target_path}`*",
            "",
        ]
        for e in self.interview_transcript:
            lines += [
                f"## Q{e['question_number']}: {e['question']}",
                "",
                f"- **Type:** {e['gap_type']}",
                f"- **Priority:** {e['priority']}",
                f"- **Code says:** {e.get('expected_from_code', 'N/A')}",
                f"- **Client says:** {e.get('client_response', 'Awaiting response')}",
                f"- **Divergence:** {'Yes' if e.get('divergence_detected') else 'No'}",
                "",
            ]
        return "\n".join(lines)

    def _render_revisions(self) -> str:
        lines = [
            "# Revisions (Sidecar)",
            "",
            "Tracks where client intent diverges from what the code does.",
            "Recipe preserves the code's version as canonical; client revisions",
            "are documented here for v2.",
            "",
            "## Divergences",
            "",
        ]
        divergences = [t for t in self.interview_transcript if t.get("divergence_detected")]
        if divergences:
            for d in divergences:
                lines += [
                    f"### Q{d['question_number']}: {d['question']}",
                    f"- Code: {d.get('expected_from_code', 'N/A')}",
                    f"- Client: {d.get('client_response', 'N/A')}",
                    "- Resolution: Pending",
                    "",
                ]
        else:
            lines.append("No divergences detected (or interview not yet conducted).")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _has_source_code(self, target: Path) -> bool:
        """Check if the target contains recognizable source files."""
        for f in target.rglob("*"):
            if (
                f.is_file()
                and f.suffix in SOURCE_EXTENSIONS
                and not any(s in f.parts for s in SKIP_DIRS)
            ):
                return True
        return False

    def _has_tests(self, target: Path) -> bool:
        patterns = ["test_*.py", "*_test.py", "*.test.ts", "*.test.js", "*.spec.*"]
        for pat in patterns:
            if next((f for f in target.rglob(pat)
                      if not any(s in f.parts for s in SKIP_DIRS)), None):
                return True
        return False

    def _calculate_confidence(self, classified: dict) -> float:
        score = 0.0
        score += min(len(classified.get("essential", [])) * 0.15, 0.40)
        score += min(len(classified.get("game_changer", [])) * 0.10, 0.30)
        score += min(len(classified.get("great", [])) * 0.05, 0.15)
        return min(score, 1.0)

    def _audit_recommendation(self, classified: dict, missing: list) -> str:
        if missing:
            return f"Cannot proceed: missing {', '.join(missing)}."
        gc = len(classified.get("game_changer", []))
        if gc >= 3:
            return "Excellent position. High-confidence extraction likely."
        if gc >= 1:
            return "Good position. Interview will fill gaps."
        return "Minimal inputs. Heavy interview required."

    def _log_unknown_task(self, task: str, details: dict):
        print(f"[{self.agent_id}] Unknown task '{task}': {details}")

    def _publish_result(self, task: str, result: str):
        self.coordinator.publish("RESULT", task, {
            "agent": self.agent_id, "task": task, "result": result,
        })


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Columbo - Codebase Forensics Agent")
    parser.add_argument("target", help="Path to the codebase to extract")
    parser.add_argument("--output", "-o", default="./recipe",
                        help="Output directory for the recipe")
    parser.add_argument("--agent-id", default="columbo")
    parser.add_argument("--redis-host", default="localhost")
    parser.add_argument("--redis-port", type=int, default=6379)
    args = parser.parse_args()

    agent = ColumboAgent(
        agent_id=args.agent_id,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        recipe_output_dir=args.output,
    )

    print("Columbo reporting for duty.")
    print(f"   Target: {args.target}")
    print(f"   Output: {args.output}")

    agent.start()
    agent._run_full_extraction({"target": args.target})
