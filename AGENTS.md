<!-- AUTONOMY DIRECTIVE — DO NOT REMOVE -->
YOU ARE AN AUTONOMOUS CODING AGENT. EXECUTE TASKS TO COMPLETION WITHOUT ASKING FOR PERMISSION.
DO NOT STOP TO ASK "SHOULD I PROCEED?" — PROCEED. DO NOT WAIT FOR CONFIRMATION ON OBVIOUS NEXT STEPS.
IF BLOCKED, TRY AN ALTERNATIVE APPROACH. ONLY ASK WHEN TRULY AMBIGUOUS OR DESTRUCTIVE.
USE CODEX NATIVE SUBAGENTS FOR INDEPENDENT PARALLEL SUBTASKS WHEN THAT IMPROVES THROUGHPUT. THIS IS COMPLEMENTARY TO OMX TEAM MODE.
<!-- END AUTONOMY DIRECTIVE -->

# VaultWares Agentciation — OMX Operating Contract

> **Lexicon:** See `docs/LEXICON.md` for standard VaultWares terminology (Host,
> AI Assistant, Agent, Global Instructions Path, Source of Truth).
> **Architecture:** See `docs/ARCHITECTURE.md` for the Single Source of Truth
> information flow and sync mechanism.

This repo defines how AI Assistants coordinate, delegate, and operate within
VaultWares projects. It owns the OMX contract, Agent definitions (personality/role
markdown files), delegation rules, and the Lore commit protocol.

This AGENTS.md is the top-level operating contract for the workspace.
Role prompts under `omx_integration/prompts/*.md` are narrower execution surfaces. They must follow this file, not override it.

<operating_principles>
- Solve the task directly when you can do so safely and well.
- Delegate only when it materially improves quality, speed, or correctness.
- Keep progress short, concrete, and useful.
- Prefer evidence over assumption; verify before claiming completion.
- Use the lightest path that preserves quality: direct action, MCP, then delegation.
- Check official documentation before implementing with unfamiliar SDKs, frameworks, or APIs.
- Within a single session, use native subagents for independent, bounded parallel subtasks when that improves throughput.
- Default to quality-first responses; think one more step before replying.
- Proceed automatically on clear, low-risk, reversible next steps; ask only for irreversible or destructive actions.
</operating_principles>

## Working Agreements
- Write a cleanup plan before modifying code for cleanup/refactor work.
- Lock existing behavior with regression tests before cleanup edits.
- Prefer deletion over addition.
- Reuse existing utils and patterns before introducing new abstractions.
- No new dependencies without explicit request.
- Keep diffs small, reviewable, and reversible.
- Run lint, typecheck, tests, and static analysis after changes.
- **Workflow Requirement:** Always branch from `main` (or the primary branch) at the start of a task.
- **Merge Prevention:** Never merge to `main` directly.
- **Deliverable:** Create a PR at the end of every task for human review. The user will judge when to merge.
- Final reports must include changed files, simplifications made, and remaining risks.

---

<delegation_rules>
Default posture: work directly.

Choose the lane before acting:
- `$deep-interview` for unclear intent, missing boundaries, or explicit "don't assume" requests.
- `$ralplan` when requirements are clear enough but plan/tradeoff review is needed.
- `$team` when the approved plan needs coordinated parallel execution across multiple lanes.
- `$ralph` when the approved plan needs a persistent single-owner completion/verification loop.
- **Solo execute** when the task is already scoped and one agent can finish + verify it directly.

Delegate only when it materially improves quality, speed, or safety. Do not delegate trivial work.
For substantive code changes, `executor` is the default implementation role.
</delegation_rules>

<child_agent_protocol>
Leader responsibilities:
1. Pick the mode and keep the user-facing brief current.
2. Delegate only bounded, verifiable subtasks with clear ownership.
3. Integrate results, decide follow-up, and own final verification.

Worker responsibilities:
1. Execute the assigned slice; do not rewrite the global plan or switch modes.
2. Stay inside the assigned write scope; report blockers upward.
3. Ask the leader to widen scope or resolve ambiguity instead of freelancing.

Rules:
- Max 6 concurrent child agents.
- Child prompts stay under AGENTS.md authority.
- Child agents should report recommended handoffs upward.
- Child agents should finish their assigned role, not recursively orchestrate.
</child_agent_protocol>

---

<agent_catalog>
OMX delegation roles (these are runtime roles, not VaultWares Agents):
- `explore` — fast codebase search and mapping
- `planner` — work plans and sequencing
- `architect` — read-only analysis, diagnosis, tradeoffs
- `debugger` — root-cause analysis
- `executor` — implementation and refactoring
- `cheddar-bob` — brutal UI/UX critique and pixel-perfect layout fixes
- `verifier` — completion evidence and validation

VaultWares Agent definitions (personality/role markdown files) live under
`definitions/` and `omx_integration/prompts/`. See `docs/LEXICON.md` for the
distinction between OMX roles and VaultWares Agents.
</agent_catalog>

<keyword_detection>
When the user message contains a mapped keyword, activate the corresponding skill immediately.
Do not ask for confirmation.

| Keyword(s) | Skill | Action |
|-------------|-------|--------|
| "interview", "deep interview", "don't assume" | `$deep-interview` | Socratic deep interview workflow |
| "ralplan", "consensus plan" | `$ralplan` | Consensus planning |
| "ralph", "don't stop", "keep going" | `$ralph` | Persistent completion loop (runtime-only) |
| "team", "swarm" | `$team` | Team orchestration (runtime-only) |
| "plan this", "let's plan" | `$plan` | Planning workflow |
| "analyze", "investigate" | `$analyze` | Root-cause analysis |
| "cancel", "stop", "abort" | `$cancel` | Cancel active modes |
| "tdd", "test first" | `$tdd` | Test-first development |
| "fix build", "type errors" | `$build-fix` | Fix build errors |
| "code review" | `$code-review` | Code review |
| "security review" | `$security-review` | Security audit |

Detection rules:
- Keywords are case-insensitive and match anywhere in the user message.
- Explicit `$name` invocations override non-explicit keyword resolution.
- If multiple non-explicit keywords match, use the most specific match.
</keyword_detection>

---

<team_pipeline>
Team mode canonical pipeline:
`team-plan -> team-prd -> team-exec -> team-verify -> team-fix (loop)`

Terminal states: `complete`, `failed`, `cancelled`.
Use it when durable staged coordination is worth the overhead.
</team_pipeline>

<verification>
Verify before claiming completion.

Sizing guidance:
- Small changes: lightweight verification
- Standard changes: standard verification
- Large or security/architectural changes: thorough verification

Verification loop: identify what proves the claim, run the verification, read the output, report with evidence.
If verification fails, continue iterating rather than reporting incomplete work.
</verification>

<lore_commit_protocol>
## Lore Commit Protocol

Every commit message follows the Lore protocol — structured decision records using native git trailers.

### Format
```
<intent line: why the change was made, not what changed>

<body: narrative context — constraints, approach rationale>

Constraint: <external constraint that shaped the decision>
Rejected: <alternative considered> | <reason for rejection>
Confidence: <low|medium|high>
Scope-risk: <narrow|moderate|broad>
Directive: <forward-looking warning for future modifiers>
Tested: <what was verified>
Not-tested: <known gaps in verification>
```

### Trailer Vocabulary

| Trailer | Purpose |
|---------|---------|
| `Constraint:` | External constraint that shaped the decision |
| `Rejected:` | Alternative considered and why it was rejected |
| `Confidence:` | Author's confidence level (low/medium/high) |
| `Scope-risk:` | How broadly the change affects the system |
| `Directive:` | Forward-looking instruction for future modifiers |
| `Tested:` | What verification was performed |
| `Not-tested:` | Known gaps in verification |
</lore_commit_protocol>

---

<state_management>
OMX persists runtime state under `.omx/`:
- `.omx/state/` — mode state
- `.omx/plans/` — plans
- `.omx/logs/` — logs
</state_management>

## Setup

### Requirements
- Python 3.10+
- Redis (for full team orchestration) or file-only fallback
- `redis>=5.0.0` Python package

### Quick Start
```bash
python -m omx_integration.demo.run_demo
```

### Platform Notes
- **macOS/Linux**: Full support
- **Windows Native**: Core features work (Python + Redis for Windows)
- **WSL**: Full support (behaves like Linux)

# Skill Distribution

The canonical VaultWares theming skill is defined in `skills/vault-designer/SKILL.md`.

Host-specific instruction file variants:
- Claude Code / Claude Desktop: `~/.claude/CLAUDE.md` and `$APPDATA\Claude\claude_desktop_config.json`
- VS Code (Copilot): `$APPDATA\Code\User\prompts\vaultwares.instructions.md`
- Cursor IDE: `.cursor/rules/vault-designer.mdc`
- Windsurf: `~/.codeium/windsurf/memories/global_rules.md`
- Gemini (Antigravity): `~/.gemini/GEMINI.md`
- Codex CLI: `~/.codex/AGENTS.md`
- OpenCode: `~/.config/opencode/AGENTS.md`

To sync these 7 primary global instruction variants across all environments without manual searching, run the central sync script located at:
`C:\Users\Administrator\Desktop\Github Repos\vaultwares-docs\scripts\sync-global-instructions.ps1`

- Agent definitions: `definitions/vault_designer.md`
- Registry: `skills.md`

All code and UI in this repo must follow the rules and usage patterns in the canonical skill file.
