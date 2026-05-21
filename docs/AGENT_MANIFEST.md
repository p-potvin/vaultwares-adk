# Agent Manifest

## Specialized AI Agents

- **definitions/text_agent.md**: Text generation, editing, manipulation, prompt engineering, VQA, workflow creation, ComfyUI/Diffusion export.
- **definitions/image_agent.md**: Image generation, editing, manipulation, masking, inpainting, workflow creation, ComfyUI/Diffusion export.
- **definitions/video_agent.md**: Video generation, editing, manipulation, frame processing, video analysis, workflow creation, ComfyUI/Diffusion export.
- **definitions/workflow_agent.md**: Workflow parsing, conversion, and export to ComfyUI/Diffusion formats.

## Forensics & Extraction Agents

- **columbo.agent.md**: Codebase forensics and recipe extraction. Transforms codebases into portable natural-language specs ("recipes") that any AI Assistant can rebuild from scratch. Monolithic HITL pipeline: audit, blind pass, sighted pass, gap map, anchored-contradiction interview, recipe composition, round-trip verification, handoff.

## Workflow Management SPA (Planned)

A single-page application (SPA) for advanced workflow management, featuring:
- Browse workflows by category
- Sort/filter workflows
- Pin workflows to top
- Add to favorites
- Create/import/delete/update/export workflows
- Backup/restore all workflows
- Option to run locally or on NVIDIA NIM VM

### Architectural Notes
- **Frontend**: React SPA (Material UI/Ant Design)
- **Backend**: FastAPI/Flask (Python), REST API for workflows, favorites, backup, NIM integration
- **Storage**: JSON/YAML files in `examples/` or DB
- **Remote Execution**: NIM VM API endpoint

### API Endpoints (Planned)
- `GET /workflows` — List workflows (with category, sort, filter)
- `POST /workflows` — Create/import workflow
- `PUT /workflows/{id}` — Update workflow
- `DELETE /workflows/{id}` — Delete workflow
- `POST /workflows/export` — Export selected workflows
- `POST /workflows/backup` — Backup all workflows
- `POST /workflows/restore` — Restore workflows from backup
- `POST /workflows/pin` — Pin/unpin workflow
- `POST /workflows/favorite` — Add/remove favorite
- `POST /workflows/run` — Run workflow (local or NIM VM)

### UI/UX Notes
- Category sidebar, sortable/filterable workflow list
- Pin/favorite toggles, batch actions (export, backup)
- Modal dialogs for create/import/export/restore
- Toggle for local vs. NIM VM execution

### Implementation Steps
1. Define API endpoints and backend models
2. Design frontend UI/UX (wireframes, components)
3. Implement backend workflow management
4. Integrate NIM VM execution option
5. Implement frontend logic and connect to API
6. Add backup/restore, export/import features
7. Testing (unit, integration, E2E)
8. Documentation and deployment

### Dependencies/Design Considerations
- React, Material UI/Ant Design, Axios (frontend)
- FastAPI/Flask, Pydantic, SQLAlchemy or file I/O (backend)
- Secure API (auth, validation)
- NIM VM API integration (auth, error handling)
- Data migration for existing workflows
- Responsive design, accessibility

All agents follow VaultWares security, privacy, and style guidelines as described in GUIDELINES.md and STYLE.md.
