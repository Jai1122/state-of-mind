# lgdebug — Project Guide for Claude

## What This Project Is

lgdebug is a **state debugger and visualizer for LangGraph agents** — "Redux DevTools for AI agents." It intercepts graph execution at node boundaries, captures state snapshots, computes structural diffs, stores traces locally in SQLite, and serves them through an interactive React UI.

This is a developer tool, not a prototype. It is designed for open-source release and production use.

## Architecture (One Paragraph)

A **LangGraph adapter** wraps each node's `.func` inside its `RunnableCallable` to capture state_before/state_after with zero node code changes. The **collector** (fully synchronous, thread-safe via `threading.Lock`) serializes states, runs the **diff engine**, decides checkpoint vs diff-only storage, and writes to **SyncSQLiteStorage** (stdlib `sqlite3`). The **debug server** (FastAPI + async `aiosqlite`) reads from the same database via WAL mode and exposes REST + WebSocket endpoints. The **replay engine** (async, used by server) reconstructs state at any step from checkpoint + diffs without re-executing the graph. A **React/TypeScript/Tailwind frontend** provides timeline, diff viewer, JSON inspector, replay slider, and routing inspector.

## Critical Architecture Rule: Sync vs Async Split

The instrumentation layer (adapter, collector, `SyncSQLiteStorage`) is **fully synchronous**. This is non-negotiable — LangGraph runs sync node functions inside its own async event loop, so any `asyncio.run()` or `await` in the instrumentation path causes deadlocks.

The server layer (FastAPI, `SQLiteStorage`, `ReplayEngine`) is **async**. It runs in its own uvicorn event loop separate from the instrumented graph.

Both layers share the same `.lgdebug/debug.db` file. WAL mode enables concurrent access.

## Directory Layout

```
src/lgdebug/
  core/
    config.py        — DebugConfig (immutable dataclass, all tunables)
    models.py        — Execution, ExecutionStep, StateDiff, RoutingDecision
    diff.py          — compute_diff() and apply_diff() — recursive structural diff
    serialization.py — serialize_state() — handles Pydantic, dataclasses, enums, circular refs
    collector.py     — DebugCollector — SYNC, thread-safe, uses SyncSQLiteStorage
  adapters/
    base.py          — FrameworkAdapter ABC
    langgraph.py     — LangGraph instrumentation, enable_debugging() public API
  storage/
    base.py          — StorageBackend async ABC (for server/replay only)
    sqlite.py        — Async SQLite (aiosqlite) — used by debug server
    sqlite_sync.py   — Sync SQLite (stdlib sqlite3) — used by instrumentation
  replay/
    engine.py        — ReplayEngine (async) — deterministic state reconstruction
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
  unit/test_storage.py         — 4 tests: CRUD + state reconstruction (sync)
  integration/test_collector.py — 2 tests: full pipeline record + replay (sync)

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

1. **Zero node modification** — the adapter patches `.func` inside LangGraph's `RunnableCallable` objects via `enable_debugging(graph)`. User node code is never touched.
2. **Fully synchronous instrumentation** — collector and storage use stdlib `sqlite3` and `threading.Lock`. No `asyncio` in the hot path. This prevents deadlocks when LangGraph runs sync nodes inside its own event loop.
3. **Checkpoint + diff storage** — full state snapshots every N steps (default 10), diffs between. Reconstruction applies at most N-1 diffs. Configurable via `DebugConfig.checkpoint_interval`.
4. **O(n) list diffing** — element-wise comparison, not LCS. LangGraph message lists are append-only in practice, so this is correct and fast.
5. **Never-fail serialization** — `serialize_state()` handles Pydantic v1/v2, dataclasses, enums, circular refs, bytes, and falls back to `repr()`. It never raises.
6. **Framework-agnostic core** — diff engine, storage, collector, replay, and server know nothing about LangGraph. Only `adapters/langgraph.py` is framework-specific.
7. **Local-first** — SQLite, no SaaS. WAL mode for concurrent reads during writes.
8. **Replay without re-execution** — `apply_diff(state, diff)` reconstructs state purely from stored data.

## LangGraph 1.0.x Internals (Critical for Adapter Work)

The adapter must understand LangGraph's internal structures:

- `graph.nodes`: `dict[str, StateNodeSpec]` — NOT plain callables
- `StateNodeSpec.runnable`: `RunnableCallable` from `langgraph._internal._runnable`
- `RunnableCallable.func`: the actual Python function to wrap
- `RunnableCallable.afunc`: optional async variant (wrap both if present)
- `graph.branches`: `defaultdict(dict)` mapping `source_node -> {name -> BranchSpec}`
- `BranchSpec.path`: `RunnableCallable` wrapping the router function
- `BranchSpec.path.func`: the actual router function to wrap

**Never replace the `RunnableCallable` itself** — only patch its `.func` attribute. Replacing the whole object breaks LangGraph's type expectations.

## Conventions

- **Python**: 3.10+, type hints everywhere, `from __future__ import annotations` in every module, line length 100, ruff for linting.
- **Sync/Async boundary**: Instrumentation layer (adapters, collector, `SyncSQLiteStorage`) is fully synchronous. Server layer (`SQLiteStorage`, `ReplayEngine`, FastAPI) is async. Never mix them.
- **Frontend**: React 18, TypeScript strict mode with `noUncheckedIndexedAccess`, Tailwind CSS, Vite bundler. Dark theme with `surface-0/1/2/3` and `accent-blue/green/red/yellow/purple` palette.
- **Tests**: pytest (sync tests). Fixtures use `tempfile.mkdtemp()` for isolated SQLite instances.
- **No Pydantic in core models** — domain models are plain dataclasses to avoid coupling. Pydantic is only a dependency for FastAPI request/response handling.

## Common Patterns

### Adding a new API endpoint
1. Add the route in `src/lgdebug/server/app.py` inside `create_app()`.
2. Add the corresponding TypeScript type in `frontend/src/types/index.ts`.
3. Add the fetch function in `frontend/src/lib/api.ts`.

### Adding a new framework adapter
1. Create `src/lgdebug/adapters/newframework.py` implementing `FrameworkAdapter`.
2. The adapter's `instrument()` method wraps the framework's execution to call `collector.record_step()` (sync) with state_before/state_after.
3. Add a public `enable_debugging()` shortcut function.

### Adding a new storage backend
1. For instrumentation: create a sync storage class (no ABC needed — duck typing).
2. For server: implement `StorageBackend` async ABC from `storage/base.py`.

## Things to Watch Out For

- **NEVER use `asyncio.run()` or `await` in instrumentation code** — LangGraph runs sync nodes inside its own event loop. This WILL deadlock.
- **Node.js version**: Frontend requires Node >= 18. The machine has nvm with v22 available — use `nvm use 22` before `npm` commands. Default is v14 which will fail on `||=` syntax.
- **`noUncheckedIndexedAccess`** in tsconfig: array indexing returns `T | undefined`. Always guard with `if (item)` or use `?.` before accessing properties.
- **LangGraph adapter wraps `.func`, not the `RunnableCallable`**: Replacing the entire `RunnableCallable` with a plain function breaks LangGraph's internal type expectations.
- **Deep copy safety**: `safe_deepcopy()` falls back to serialize round-trip when `copy.deepcopy()` fails (some LLM response objects don't support it).
- **SQLite WAL files**: `.db-wal` and `.db-shm` are expected alongside the `.db` file. The `lgdebug clean` command removes all three.

## Non-Goals (Don't Build These)

- Prompt evaluation platform
- Cost analytics / token tracking
- Model performance monitoring
- SaaS / cloud deployment
- Multi-tenant access control

This is a **state debugger**. It answers "how did state change across nodes?" not "how well did the LLM perform?"
