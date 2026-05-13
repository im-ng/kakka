# Kakka — Agent Instructions

## Architecture

Two-package monorepo (no workspace tooling):

- `backend/` — FastAPI async + SQLAlchemy ORM + aiosqlite + SQLite
- `frontend/` — Astro SPA + TailwindCSS v4 + **vanilla JS only** (no React/Preact/Svelte)

Four tabs: Todos list, Kanban board, Knowledge Graph (vis-network), Chat (KG query engine).

Data flow: Frontend fetches `API_BASE/api/*` → FastAPI routers → SQLAlchemy async → SQLite.

KG sync hooks (`kg_sync.py`) keep Entity/Triple tables in sync with Task CRUD.

## Gotchas

- **Column `grp` in DB, `project` in API/Pydantic**: The `Task` ORM model stores `project` as column `grp`. `task_to_dict()` maps it. Don't query `Task.project` — use `Task.grp`.
- **Route ordering**: `/api/tasks/reorder` must be registered BEFORE `/api/tasks/{task_id}` in `routers.py` or FastAPI will match the path parameter first.
- **`_format_response` returns a 3-tuple**: `(content, task_refs, actions)`. `query_kg()` must return this tuple directly — wrapping it in another tuple causes Pydantic 500 errors.
- **Frontend API base**: Hardcoded as `http://0.0.0.0:8000/api` in `index.astro` (not `localhost`).
- **`done` is derived**: `done = status == "done"`, set on both create and update. Not independently writable.
- **HTML5 DnD handlers**: Kanban column drop handlers attach to static HTML, initialized ONCE. Not per-render.
- **Chat is not LLM**: `chat.py` is pure Python pattern matching (regex + KG queries). No Ollama/httpx dependency.
- **`TaskRef.changed: bool`**: Chat responses include this flag; frontend reloads task list when `true`.

## Tech Constraints

- **Vanilla JS only** — no Preact, React, Svelte, or any framework. All interactivity in a single `<script is:inline>` in `index.astro`.
- **TailwindCSS v4** — not v3. Uses `@import "tailwindcss"`, `@theme { }` block, `@custom-variant dark`. No `tailwind.config.js`.
- **HTML5 native Drag API** — no drag libraries.
- **Inline SVGs only** — no external images, no icon font CDN (except raven.png favicon).
- **Dark mode**: class-based (`class="dark"` on `<html>`), persisted `localStorage` key `df-theme`. Light mode is default (un-prefixed), `dark:` overrides. No `light:` prefix.
- **Font size cycle**: 16→19→23px, persisted `localStorage` key `df-font`.
- **Icons**: inline SVG only, no icon fonts, no CDN.

## Dev Commands

```bash
# Backend (port 8000)
cd backend && python3 -m uvicorn main:app --port 8000 --reload

# Frontend (port 4321) — must use bun, not npm
cd frontend && bun run dev

# Production build
cd frontend && bun run build    # outputs to frontend/dist/
# Then: backend serves frontend/dist/ via StaticFiles at /

# Podman
podman build -f Dockerfile -t kakka:0.1 .
podman run -p 8000:8000 -v ./kakka_data/kakka.db:/app/backend/kakka.db localhost/kakka:0.1
```

Both servers run simultaneously. No tests, no lint, no typecheck configs exist.

## Backend Files

| File | Purpose |
|---|---|
| `main.py` | FastAPI app, lifespan, CORS, StaticFiles mount |
| `database.py` | SQLAlchemy async models (Task, Entity, Triple), session, seed data |
| `models.py` | Pydantic schemas (TaskCreate/Update/Out, ChatRequest/Response, TaskRef, GraphData) |
| `routers.py` | All `/api/` endpoints: tasks CRUD, graph, chat |
| `chat.py` | KG query engine: regex pattern matching, task creation, status actions |
| `kg_sync.py` | Sync hooks: `sync_task_to_graph()`, `sync_task_update_graph()`, `sync_task_delete_graph()` |
| `start.sh` | `uv run uvicorn main:app --host 0.0.0.0 --port 8000` |

## Frontend Files

| File | Purpose |
|---|---|
| `src/pages/index.astro` | Entire SPA (~1300 lines): markup + all vanilla JS |
| `src/layouts/Layout.astro` | HTML shell, fonts, theme CSS, animations, scrollbar, vis-network import |
| `src/styles/global.css` | TailwindCSS v4 `@theme` tokens + `@custom-variant dark` |
| `astro.config.mjs` | Astro config with TailwindCSS v4 Vite plugin |
| `public/vis-network.min.js` | vis-network standalone UMD bundle |

## Knowledge Graph

Three tables in SQLite alongside `tasks`:

- **Entity** — `id` (string like `task:1`, `tag:work`, `project:kakka`, `status:todo`), `name`, `type`, `properties` (JSON), `created_at`
- **Triple** — `id`, `subject`, `predicate` (`has_tag`, `belongs_to`, `has_status`), `object`, `valid_from`, `valid_to` (null = current), `confidence`, `source_task_id`

Sync hooks fire on task create/update/delete to maintain entity/triple consistency. Old facts get `valid_to` timestamp (temporal KG).

Graph view: vis-network force-directed. Node colors by type: task=sage, tag=amber, project=emerald, concept=slate.

Chat: pattern-matching engine in `chat.py`. Detects greetings, tag/status/project filters, entity lookups, keyword search, task ID refs. Status actions: `mark #3 as done`, `start #1`, `reopen #5`. Task creation: `add task "title" with description X`.

## Design Tokens

Defined in `frontend/src/styles/global.css`:

- navy/navy-light/navy-lighter, slate/slate-light/slate-dark, sage/sage-light/sage-dark/sage-pale, mint/mint-light/mint-dark
- Fonts: DM Sans (`--font-sans`), Playfair Display (`--font-display`)
- `design.html` is the reference wireframe — match its interactions, don't redesign