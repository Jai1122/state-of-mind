# lgdebug — Project Guide for Claude

## What This Project Is

lgdebug is a **state debugger and visualizer for LangGraph agents** — "Redux DevTools for AI agents." It intercepts graph execution at node boundaries, captures state snapshots, computes structural diffs, stores traces locally in SQLite, and serves them through an interactive React UI.

This is a developer tool, not a prototype. It is designed for open-source release and production use.

## Architecture (One Paragraph)

A **LangGraph adapter** wraps each node function to capture state_before/state_after with zero node code changes. The **collector** serializes states, runs the **diff engine**, decides checkpoint vs diff-only storage, writes to the **SQLite storage** layer, and broadcasts to WebSocket subscribers. The **replay engine** reconstructs state at any step from checkpoint + diffs without re-executing the graph. A **FastAPI server** exposes REST + WebSocket endpoints. A **React/TypeScript/Tailwind frontend** provides timeline, diff viewer, JSON inspector, replay slider, and routing inspector.

## Directory Layout

```
src/lgdebug/
  core/
    config.py        — DebugConfig (immutable dataclass, all tunables)
    models.py        — Execution, ExecutionStep, StateDiff, RoutingDecision
    diff.py          — compute_diff() and apply_diff() — recursive structural diff
    serialization.py — serialize_state() — handles Pydantic, dataclasses, enums, circular refs
    collector.py     — DebugCollector — central coordinator, module-level singleton
  adapters/
    base.py          — FrameworkAdapter ABC
    langgraph.py     — LangGraph instrumentation, enable_debugging() public API
  storage/
    base.py          — StorageBackend ABC
    sqlite.py        — SQLite with WAL, checkpoint+diff strategy
  replay/
    engine.py        — ReplayEngine — deterministic state reconstruction
  server/
    app.py           — FastAPI app factory, REST + WebSocket endpoints
  cli/
    main.py          — CLI: run, server, list, show, clean

frontend/src/
  App.tsx                      — Root component, execution selection, WebSocket connection
  components/
    ExecutionList.tsx           — Sidebar listing executions
    ExecutionView.tsx           — Main detail panel (orchestrates tabs + timeline)
    Timeline.tsx                — Horizontal node chain [Start] → node → ... → [End]
    DiffViewer.tsx              — Changed/added/removed entries with color coding
    JsonViewer.tsx              — Collapsible JSON tree with change path highlighting
    ReplaySlider.tsx            — Step scrubbing slider with arrow buttons
    RoutingInspector.tsx        — Conditional edge evaluation display
  hooks/useWebSocket.ts        — Auto-reconnecting WebSocket hook
  lib/api.ts                   — Typed fetch wrapper for backend endpoints
  types/index.ts               — TypeScript interfaces matching Python models

tests/
  unit/test_diff.py            — 14 tests: compute_diff + apply_diff
  unit/test_serialization.py   — 14 tests: all type handlers + edge cases
  unit/test_storage.py         — 4 tests: CRUD + state reconstruction
  integration/test_collector.py — 2 tests: full pipeline record + replay

examples/
  research_agent.py            — LangGraph integration demo with simulation fallback
```

## Development Commands

```bash
# Python setup
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests (34 total, all should pass)
pytest                         # full suite
pytest tests/unit/test_diff.py # specific module

# Frontend setup (requires Node >= 18, use nvm use 22)
cd frontend && npm install && npm run build

# Run the debug server (serves API + built frontend)
lgdebug run                    # opens browser at http://127.0.0.1:6274
lgdebug server                 # headless API only

# Inspect recorded data
lgdebug list                   # list executions
lgdebug show <execution_id>    # show timeline for one execution
lgdebug clean                  # delete .lgdebug/debug.db

# Run the example (simulation mode, no LangGraph needed)
python examples/research_agent.py

# Frontend dev mode (proxies API to :6274)
cd frontend && npm run dev     # vite dev server on :6275
```

## Key Design Decisions

1. **Zero node modification** — the adapter wraps node callables via `enable_debugging(graph)`. User node code is never touched.
2. **Checkpoint + diff storage** — full state snapshots every N steps (default 10), diffs between. Reconstruction applies at most N-1 diffs. Configurable via `DebugConfig.checkpoint_interval`.
3. **O(n) list diffing** — element-wise comparison, not LCS. LangGraph message lists are append-only in practice, so this is correct and fast.
4. **Never-fail serialization** — `serialize_state()` handles Pydantic v1/v2, dataclasses, enums, circular refs, bytes, and falls back to `repr()`. It never raises.
5. **Framework-agnostic core** — diff engine, storage, collector, replay, and server know nothing about LangGraph. Only `adapters/langgraph.py` is framework-specific.
6. **Local-first** — SQLite, no SaaS. WAL mode for concurrent reads during writes.
7. **Replay without re-execution** — `apply_diff(state, diff)` reconstructs state purely from stored data.

## Conventions

- **Python**: 3.10+, type hints everywhere, `from __future__ import annotations` in every module, line length 100, ruff for linting.
- **Async**: storage and collector are async (aiosqlite). Adapters bridge sync node functions to async collector via `asyncio.get_running_loop().create_task()` or `asyncio.run()` fallback.
- **Frontend**: React 18, TypeScript strict mode with `noUncheckedIndexedAccess`, Tailwind CSS, Vite bundler. Dark theme with `surface-0/1/2/3` and `accent-blue/green/red/yellow/purple` palette.
- **Tests**: pytest + pytest-asyncio with `asyncio_mode = "auto"`. Fixtures use `tempfile.TemporaryDirectory` for isolated SQLite instances.
- **No Pydantic in core models** — domain models are plain dataclasses to avoid coupling. Pydantic is only a dependency for FastAPI request/response handling.

## Common Patterns

### Adding a new API endpoint
1. Add the route in `src/lgdebug/server/app.py` inside `create_app()`.
2. Add the corresponding TypeScript type in `frontend/src/types/index.ts`.
3. Add the fetch function in `frontend/src/lib/api.ts`.

### Adding a new framework adapter
1. Create `src/lgdebug/adapters/newframework.py` implementing `FrameworkAdapter`.
2. The adapter's `instrument()` method wraps the framework's execution to call `collector.record_step()` with state_before/state_after.
3. Add a public `enable_debugging()` shortcut function.

### Adding a new storage backend
1. Create `src/lgdebug/storage/newbackend.py` implementing `StorageBackend`.
2. Must implement `get_state_at_step()` with checkpoint+diff reconstruction logic (or can use `apply_diff` from `core/diff.py`).

## Things to Watch Out For

- **Node.js version**: Frontend requires Node >= 18. The machine has nvm with v22 available — use `nvm use 22` before `npm` commands. Default is v14 which will fail on `||=` syntax.
- **`noUncheckedIndexedAccess`** in tsconfig: array indexing returns `T | undefined`. Always guard with `if (item)` or use `?.` before accessing properties.
- **Sync/async bridge in adapter**: LangGraph nodes can be sync or async. The wrapper must match the original's nature. Sync wrappers use `create_task()` or `asyncio.run()` fallback to call the async collector.
- **Deep copy safety**: `safe_deepcopy()` falls back to serialize round-trip when `copy.deepcopy()` fails (some LLM response objects don't support it).
- **SQLite WAL files**: `.db-wal` and `.db-shm` are expected alongside the `.db` file. The `lgdebug clean` command removes all three.

## Non-Goals (Don't Build These)

- Prompt evaluation platform
- Cost analytics / token tracking
- Model performance monitoring
- SaaS / cloud deployment
- Multi-tenant access control

This is a **state debugger**. It answers "how did state change across nodes?" not "how well did the LLM perform?"
