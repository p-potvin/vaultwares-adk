# VaultWares Single Source of Truth — Architecture

How AI Assistants receive VaultWares instructions regardless of which Host they
run in.

## Information Flow

```
Global Instructions Path (per Host)
  |
  v
vaultwares-docs/AGENTS.md          <-- Tier 1: company rules, pointers
  |
  +-- vault-themes/AGENTS.md       <-- Tier 2: design tokens, brand, visual rules
  +-- vaultwares-agentciation/AGENTS.md  <-- Tier 2: OMX contract, Agent catalog, Lore protocol
  +-- agent-ledger/AGENTS.md       <-- Tier 2: ledger protocol, agent header template
  |
  v
<repo>/AGENTS.md                   <-- Repo-specific rules (override higher tiers)
```

## Tier Responsibilities

| Tier | Repo | Governs |
|------|------|---------|
| 1 | `vaultwares-docs` | Company overview, lexicon pointer, mandatory protocols (ledger, credit optimization), pointers to tier-2 repos |
| 2 | `vault-themes` | All design tokens, brand direction, visual rules, theme manager, consumer repo policy, quality gates |
| 2 | `vaultwares-agentciation` | OMX operating contract, Agent definitions, delegation rules, Lore commit protocol, keyword detection, skill distribution |
| 2 | `agent-ledger` | Agent header template, ledger recording protocol, event schema, render/impact scripts |
| 3 | Each repo | Repo-specific rules only (e.g., "Firefox-first" in vault-central, tech stack constraints) |

## Sync Mechanism

A PowerShell script (`vaultwares-docs/scripts/sync-global-instructions.ps1`)
maintains VaultWares content at each Host's Global Instructions Path.

**How it works:**
1. Reads `vaultwares-docs/AGENTS.md` as source content
2. Strips markdown formatting to plain text for JSON-based targets
3. Wraps content in `<!-- VAULTWARES-SYNC:START -->` / `<!-- VAULTWARES-SYNC:END -->` markers
4. Writes to each Host path, preserving any user content outside the markers
5. Runs as a Windows Scheduled Task (daily + on logon)

**Design decisions:**
- Script lives in `vaultwares-docs` because it is the tier-1 SoT owner
- Script writes *copies* to each Global Instructions Path (no symlinks — avoids permission issues)
- Marker-based injection means the script never destroys user-added content
- `CLAUDE.md` workspace/repo files are excluded — they are manually maintained and checked into Git

## Host Path Registry

| Host | Global Instructions Path | File Name | Sync Method |
|------|------------------------|-----------|-------------|
| Claude Code | `~/.claude/CLAUDE.md` | `CLAUDE.md` | Marker injection |
| VS Code (Copilot) | `%APPDATA%/Code/User/prompts/` | `vaultwares.instructions.md` | Full file (dedicated) |
| Windsurf | `~/.codeium/windsurf/memories/global_rules.md` | `global_rules.md` | Marker injection |
| Antigravity / Gemini CLI | `~/.gemini/GEMINI.md` | `GEMINI.md` | Marker injection (shared — known limitation) |
| Codex CLI | `~/.codex/AGENTS.md` | `AGENTS.md` | Full file (dedicated) |
| OpenCode | `~/.config/opencode/AGENTS.md` | `AGENTS.md` | Full file (dedicated) |
| Claude Desktop | `%APPDATA%/Claude/claude_desktop_config.json` | JSON field | Plain-text injection into JSON (manual fallback if structure changes) |

**Known limitation:** Antigravity and Gemini CLI share `~/.gemini/GEMINI.md`.
Both are Google products so the content is compatible, but edits by one may be
overwritten by the sync script.

## Scheduled Task Pattern

When creating Windows Scheduled Tasks for VaultWares scripts, use the headless
conhost pattern so no console window flashes on screen:

```
Execute:  C:\Windows\System32\conhost.exe
Arguments: --headless powershell.exe -NoProfile -WindowStyle Hidden -NonInteractive -ExecutionPolicy Bypass -File "<path>"
```

The `conhost.exe --headless` wrapper prevents the terminal window from appearing.
`-WindowStyle Hidden` is belt-and-suspenders in case conhost is unavailable.

## Principles

- **Link, don't duplicate.** Tier-1 points to tier-2. Tier-2 owns its domain. Repos point up.
- **Narrower scope wins.** A repo AGENTS.md overrides workspace. A directory AGENTS.md overrides repo.
- **Keep repo AGENTS.md lean.** Consumer repos should have <30 lines unless they are a tier-2 SoT.
- **The file name is a standard.** `AGENTS.md` is the Linux Foundation open standard name. Do not rename it.
