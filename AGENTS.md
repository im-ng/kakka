# Kakka — Agent Instructions

## Architecture

Two-package monorepo:

- `backend/` — FastAPI (Python) + SQLite REST API
- `frontend/` — Astro + TailwindCSS 4, client-side rendered SPA (no SSR)

## Tech Stack (fixed, not negotiable)

- Frontend: Astro with **vanilla JS only** (no Preact, no React, no Svelte)
- Styling: TailwindCSS **v4** (not v3 — syntax and config differ)
- Drag & drop: HTML5 native Drag API (no libraries)
- Backend: FastAPI + SQLite
- Icons/logos: **inline SVGs only** — no external images, no icon font CDN (SPEC.md)
- Use the `frontend-design` skill when building UI (SPEC.md)

## Design System

Dark mode: class-based toggle (`class="dark"` on `<html>`), persisted in `localStorage` key `df-theme`.

Custom Tailwind colors (from `design.html` wireframe):

- navy: `#19183B` / light `#22214A` / lighter `#2C2B5E`
- slate: `#708993` / light `#8BA3AC` / dark `#5A717B`
- sage: `#A1C2BD` / light `#B8D4CF` / dark `#7FA8A2` / pale `#D4E8E4`
- mint: `#E7F2EF` / light `#F0F7F5` / dark `#D0E4DF`

Fonts: DM Sans (body), Playfair Display (headings).

Two ColorHunt palettes in `DESIGN.md` — light palette (#355872, #7AAACE, #9CD5FF, #F7F8F0) and dark palette (#19183B, #708993, #A1C2BD, #E7F2EF). The custom Tailwind tokens above are the resolved synthesis of both.

## Reference Wireframe

`design.html` is a **592-line working prototype** with full task CRUD, kanban DnD, theme toggle, and toast system. Match its interactions, animations (fadeUp, card-lift, modal transitions), and visual fidelity. Do not redesign — implement what it shows.

## Task Data Model

| Field       | Type       | Notes                          |
| ----------- | ---------- | ------------------------------ |
| id          | int        | Auto-increment                 |
| title       | str        | Required                       |
| description | str        | Optional                       |
| status      | str        | `todo` \| `progress` \| `done` |
| done        | bool       | Derived from status            |
| tags        | JSON array | e.g. `["work","urgent"]`       |
| group       | str        | Optional grouping              |
| created_at  | datetime   | Auto-set                       |
| updated_at  | datetime   | Auto-updated                   |

## REST API

All endpoints under `/api/`:

- `GET /api/tasks` — list (filter by tag, date, status via query params)
- `POST /api/tasks` — create
- `PUT /api/tasks/{id}` — update (edit fields, move kanban status)
- `DELETE /api/tasks/{id}` — delete
- `GET /api/tags` — list all distinct tags in use

Kanban card moves persist via `PUT /api/tasks/{id}` with the new `status` value.

## Dev Commands

Backend:

```bash
cd backend && python3 -m uvicorn main:app --port 8000 --reload
```

Frontend (uses **bun**, not npm):

```bash
cd frontend && bun run dev       # dev server on :4321
cd frontend && bun run build     # production build to dist/
```

Both servers must run simultaneously. Frontend fetches from `http://localhost:8000/api`.

## Backend File Map

- `backend/main.py` — FastAPI app entry point, CORS config, router mount
- `backend/database.py` — SQLite connection, schema init, seed data
- `backend/models.py` — Pydantic schemas (TaskCreate, TaskUpdate, TaskOut)
- `backend/routers.py` — All REST endpoints under `/api/`

## Frontend File Map

- `frontend/src/layouts/Layout.astro` — HTML shell, theme CSS, fonts, scrollbar styles
- `frontend/src/pages/index.astro` — Single-page app: all markup + vanilla JS client
- `frontend/src/styles/global.css` — TailwindCSS v4 import + `@theme` custom tokens + `@custom-variant dark`
- `frontend/astro.config.mjs` — Astro config with TailwindCSS v4 Vite plugin

## Key Architecture Decisions

- **TailwindCSS v4 dark mode**: Uses `@custom-variant dark (&:where(.dark, .dark *))` in `global.css` for class-based dark mode toggle. The `dark:` prefix in classes activates when `<html>` has `class="dark"`.
- **No `light:` prefix**: Light mode is the default (un-prefixed) style. `dark:` overrides apply when the dark class is present. The wireframe's `light:` classes were converted to base classes.
- **Vanilla JS**: All interactivity (CRUD, DnD, theme, toasts, filters) is in a single `<script is:inline>` block inside `index.astro`. No React/Preact/Svelte.
- **API calls**: Frontend fetches from `http://localhost:8000/api` using native `fetch()`. The `api()` helper wraps all requests.
- **Theme persistence**: `localStorage` key `df-theme` stores `'light'` or `'dark'`.
- **SQLite DB file**: `backend/kakka.db` — auto-created on first startup with 7 seed tasks.

## Requirements Checklist

- [x] Kanban drag-and-drop state persists to backend (PUT /api/tasks/{id} with new status)
- [x] Tasks filterable by tags and date (both list and kanban views)
- [x] Task dialog supports: edit, tag, group, delete, description, save
- [x] Dark/light mode toggle with localStorage persistence
- [x] Inline SVGs only — no external images, no icon fonts
- [x] Animations: fadeUp, card-lift, modal transitions, toast notifications
- [x] Mobile: responsive grid (1-col kanban on mobile, 3-col on md+)
- [ ] Site must look modern with nice animations — visual polish review needed
- [ ] End-to-end browser testing needed

## Behavioral guidelines

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

Tradeoff: These guidelines bias toward caution over speed. For trivial tasks, use judgment.

1. Think Before Coding
   Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

State your assumptions explicitly. If uncertain, ask.
If multiple interpretations exist, present them - don't pick silently.
If a simpler approach exists, say so. Push back when warranted.
If something is unclear, stop. Name what's confusing. Ask.

2. Simplicity First
   Minimum code that solves the problem. Nothing speculative.

No features beyond what was asked.
No abstractions for single-use code.
No "flexibility" or "configurability" that wasn't requested.
No error handling for impossible scenarios.
If you write 200 lines and it could be 50, rewrite it.
Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

3. Surgical Changes
   Touch only what you must. Clean up only your own mess.

When editing existing code:

Don't "improve" adjacent code, comments, or formatting.
Don't refactor things that aren't broken.
Match existing style, even if you'd do it differently.
If you notice unrelated dead code, mention it - don't delete it.
When your changes create orphans:

Remove imports/variables/functions that YOUR changes made unused.
Don't remove pre-existing dead code unless asked.
The test: Every changed line should trace directly to the user's request.

4. Goal-Driven Execution
   Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

"Add validation" → "Write tests for invalid inputs, then make them pass"
"Fix the bug" → "Write a test that reproduces it, then make it pass"
"Refactor X" → "Ensure tests pass before and after"
For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

These guidelines are working if: fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
