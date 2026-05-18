# VaultWares Lexicon

Standard terminology for all VaultWares projects. AI Assistants and humans use
these terms consistently across documentation, code comments, and commit messages.

## Core Terms

| Term | Definition | Examples |
|------|-----------|----------|
| **Host** | Application container that runs an AI Assistant. The Host provides the UI, file access, and tool integrations. | VS Code, Claude Desktop, Windsurf, Antigravity, JetBrains IDEs, terminal (CLI) |
| **AI Assistant** | The LLM service powering the interaction inside a Host. One Host may support multiple AI Assistants. | Claude, ChatGPT, Gemini, Codex, Copilot, Manus |
| **Agent** | A personality or role instance defined as a markdown file. An Agent shapes how an AI Assistant behaves in a specific context. Agents are created by humans and consumed by AI Assistants. | `lonely_manager`, `extroverts`, `cheddar-bob`, `vault-designer`, `image_agent` |
| **Global Instructions Path** | The first file an AI Assistant reads on startup. Location varies by Host. The sync script maintains VaultWares content at each path. | `~/.claude/CLAUDE.md`, `~/.gemini/GEMINI.md`, `~/.codex/AGENTS.md` |
| **Source of Truth (SoT)** | Canonical location for a category of information. Higher-tier SoTs take precedence. | Tier 1: `vaultwares-docs`. Tier 2: `vault-themes`, `vaultwares-adk`, `agent-ledger` |

## Disambiguation

These terms are commonly confused or overloaded:

| Avoid | Use Instead | Why |
|-------|------------|-----|
| "Agent" when referring to Claude, ChatGPT, etc. | **AI Assistant** | "Agent" is reserved for role instances (markdown definitions) |
| "Agent" when referring to VS Code, Claude Desktop, etc. | **Host** | Hosts are containers, not intelligence |
| "Bot" | **AI Assistant** or **Agent** depending on context | "Bot" is ambiguous and informal |
| "Model" (when referring to the full service) | **AI Assistant** | "Model" refers to the underlying LLM weights, not the service layer |
| "Plugin" or "Extension" (for Agent definitions) | **Agent** | Agents are behavioral definitions, not code plugins |

## AGENTS.md (the file)

The filename `AGENTS.md` follows the Linux Foundation open standard adopted by
Codex, Jules, Cursor, Windsurf, and 20K+ repositories. The file name does not
imply that its contents are only about Agents. It is the standard location for
AI Assistant instructions at any scope (workspace, repo, directory).

## Scope Hierarchy

Instructions cascade from broad to narrow. Narrower scope overrides broader:

1. **Global Instructions Path** — machine-wide defaults for a specific Host
2. **Workspace root** — `Github Repos/AGENTS.md` applies to all repos
3. **Repo root** — `<repo>/AGENTS.md` applies to that repo
4. **Directory** — `<repo>/subdir/AGENTS.md` applies to that subtree
5. **Agent definition** — `definitions/<agent>.md` or `omx_integration/prompts/*.md`
