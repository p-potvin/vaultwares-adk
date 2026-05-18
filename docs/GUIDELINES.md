# Agent Creation Guidelines

When creating a new agent in the `vaultwares-adk` repository, adhere to the following rules and structure:

## 1. Agent Markdown File (`<agent-name>.agent.md`)
- **Location:** All new agents must be created in this repository (`vaultwares-adk`).
- **Naming:** Use original, creative names (e.g., `cheddar-bob.agent.md`).
- **Frontmatter Attributes:** 
  - Ensure the agent's definition contains required configurations.
  - *Note: While standard VS Code `.agent.md` schema supports `tools`, it may lint against `skills` or `mcps` properties. If utilizing custom parsed pipelines, add these carefully, or define them explicitly in the markdown body.*
- **Personality over Role:** Focus on describing the agent's personality traits, quirks, and background, rather than just the dry nature of their work.
- **Relatability:** Actively relate the new agent to at least one other existing agent in the repository (e.g., "spars with the backend performance optimization agent").
- **Lifecycle:** Clearly describe the agent's execution lifecycle (e.g., Boot up -> Aggressively Scan -> Critique -> Shut down).

## 2. Python Logic Loop (`<agent-name>.py`)
- Accompanied by the markdown file, always create a Python script of the exact same name (e.g., `cheddar-bob.py`).
- **Purpose:** Customize the logic loop of the agent.
- **Execution:** Hook in tool calls at specific lifecycle stages (e.g., invoking `take_screenshot` before running the analysis loop).

## 3. Tooling
- Always give the agent explicit access or instructions for the UI tools, MCPs, and skills they need to function.