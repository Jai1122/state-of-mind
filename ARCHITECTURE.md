# lgdebug Architecture

> Redux DevTools for LangGraph Agents

## 1. System Overview

lgdebug is a state debugger for LangGraph applications. It intercepts graph
execution, captures state snapshots at every node boundary, computes structural
diffs, stores everything locally, and serves it through an interactive web UI.

```
┌─────────────────────────────────────────────────────────────────┐
│                     User's LangGraph App                        │
│                                                                 │
│   graph = enable_debugging(graph)   ← ONE LINE integration     │
│   app = graph.compile()                                        │
│   result = app.invoke(state)                                   │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────┐     ┌────────────────────────────────┐
│   Instrumentation Layer  │     │         Debug Server           │
│                          │     │                                │
│  ┌────────────────────┐  │     │  FastAPI + WebSocket           │
│  │  LangGraph Adapter │──┼────▶│  GET /api/executions           │
│  └────────────────────┘  │     │  GET /api/executions/{id}/...  │
│  ┌────────────────────┐  │     │  WS  /ws/live                  │
│  │  State Serializer  │  │     └───────────────┬────────────────┘
│  └────────────────────┘  │                     │
│  ┌────────────────────┐  │                     ▼
│  │    Diff Engine     │  │     ┌────────────────────────────────┐
│  └────────────────────┘  │     │      Frontend Visualizer       │
│  ┌────────────────────┐  │     │                                │
│  │    Collector       │──┼──┐  │  React + TypeScript + Tailwind │
│  └────────────────────┘  │  │  │  ┌──────────┐ ┌────────────┐  │
└──────────────────────────┘  │  │  │ Timeline  │ │ Diff View  │  │
                              │  │  └──────────┘ └────────────┘  │
                              │  │  ┌──────────┐ ┌────────────┐  │
                              ▼  │  │JSON View │ │ Replay     │  │
┌──────────────────────────┐  │  │  └──────────┘ └────────────┘  │
│      Storage Layer       │  │  └────────────────────────────────┘
│                          │  │
│  SQLite (WAL mode)       │◀─┘
│  ┌────────────────────┐  │
│  │   executions       │  │
│  │   steps            │  │
│  │   routing_decisions│  │
│  └────────────────────┘  │
│                          │
│  Checkpoint + Diff       │
│  strategy for storage    │
│  efficiency              │
└──────────────────────────┘
```

## 2. Core Abstraction

The fundamental unit of debugging is the **state transition**:

```
State_t → (node execution) → State_t+1
```

We capture:
- `state_before` — deep copy of state entering the node
- `state_after` — state after the node produces its update
- `state_diff` — structural diff showing only what changed
- `node_name` — which node executed
- `timestamp` — when it happened
- `execution_id` — which graph run this belongs to

## 3. Component Details

### 3.1 Instrumentation Layer (`src/lgdebug/adapters/`)

**Design decision:** Zero node modification.

The LangGraph adapter wraps each node's callable function:

```python
# Before wrapping:
node("planner") → planner_fn(state) → partial_update

# After wrapping:
node("planner") → wrapper(state) →
    1. deep_copy(state) → state_before
    2. planner_fn(state) → partial_update
    3. merge(state_before, partial_update) → state_after
    4. collector.record_step(state_before, state_after)
    5. return partial_update  ← unchanged
```

The wrapper preserves sync/async nature of the original function so LangGraph's
execution engine is unaffected.

**Framework-agnostic design:** The `FrameworkAdapter` base class defines the
interface. LangGraph is the first adapter. Future adapters for CrewAI, OpenAI
Agents SDK, or custom workflows implement the same interface.

### 3.2 State Serialization (`src/lgdebug/core/serialization.py`)

LangGraph state can contain arbitrary Python objects. The serializer converts
anything into JSON-safe structures:

| Input Type | Output |
|---|---|
| dict, list, str, int, float, bool, None | Pass through |
| Pydantic model (v1 or v2) | `.model_dump()` / `.dict()` |
| dataclass | `dataclasses.asdict()` |
| Enum | `.value` |
| datetime | `.isoformat()` |
| UUID | `str()` |
| set/frozenset | sorted list |
| bytes | `"<bytes len=N>"` |
| Circular reference | `"<circular reference>"` |
| Unknown | `repr()` fallback |

**Safety:** Circular references are detected via `id()` tracking. Large blobs
are truncated. The serializer never raises — it always produces usable output.

### 3.3 Diff Engine (`src/lgdebug/core/diff.py`)

Recursive structural diff algorithm:

- **Dicts:** set difference on keys (added/removed), recurse on shared keys.
- **Lists:** element-wise comparison up to `min(len)`, then tail as added/removed.
- **Scalars:** direct equality.

Output format:
```json
{
  "changed": [{"path": "intent", "old_value": "research", "new_value": "summarize"}],
  "added": [{"path": "summary", "value": "..."}],
  "removed": [{"path": "temp_data", "value": "..."}]
}
```

**Why not LCS for lists?** LangGraph message lists are append-only in practice.
Element-wise comparison is O(n) vs O(n²) for LCS, and produces clearer diffs
for the common case.

The diff engine also implements `apply_diff()` — the inverse operation used by
the replay engine to reconstruct state from checkpoint + diffs.

### 3.4 Collector (`src/lgdebug/core/collector.py`)

Central coordinator between adapters and storage. Responsibilities:

1. Manages execution lifecycle (start/end).
2. Serializes and deep-copies state.
3. Computes diffs.
4. Decides checkpoint vs diff-only storage (every N steps).
5. Persists to storage.
6. Broadcasts events to WebSocket subscribers for live UI updates.

Thread-safe via asyncio locks.

### 3.5 Storage Layer (`src/lgdebug/storage/`)

**Choice: SQLite with WAL mode.**

Why SQLite:
- Zero configuration — single file, no server.
- Local-first — works offline, no SaaS dependency.
- WAL mode — concurrent reads during writes (live UI while recording).
- Adequate performance for typical agent executions (< 1000 steps).

Schema:
```sql
executions(execution_id, graph_name, started_at, ended_at, status, initial_state, final_state, step_count)
steps(step_id, execution_id, node_name, step_index, state_before, state_after, state_diff, is_checkpoint)
routing_decisions(step_id, execution_id, source_node, target_node, condition_description, evaluated_value)
```

**Checkpoint strategy:** Full state snapshots every N steps (default: 10).
Non-checkpoint steps store only the diff. Reconstruction walks backward to
nearest checkpoint, then applies diffs forward. At most N-1 diffs to apply.

**Abstract base:** `StorageBackend` ABC allows future backends (PostgreSQL,
S3-backed, in-memory) without changing any other component.

### 3.6 Replay Engine (`src/lgdebug/replay/engine.py`)

Deterministic state reconstruction:

```
state_at(step_k) = checkpoint_state + diff_{cp+1} + diff_{cp+2} + ... + diff_k
```

Key operations:
- `get_state_at_step(execution_id, step_index)` — single step reconstruction
- `get_full_timeline(execution_id)` — all states for replay slider
- `compare_steps(execution_id, step_a, step_b)` — arbitrary step comparison

**No re-execution:** The replay engine NEVER calls node functions. It purely
reconstructs state from stored data.

### 3.7 Debug Server (`src/lgdebug/server/app.py`)

FastAPI backend serving execution data:

| Endpoint | Description |
|---|---|
| `GET /api/executions` | List all executions |
| `GET /api/executions/{id}` | Execution details |
| `GET /api/executions/{id}/steps` | All steps |
| `GET /api/executions/{id}/state/{step}` | Reconstructed state at step |
| `GET /api/executions/{id}/timeline` | Full timeline with states |
| `GET /api/executions/{id}/routing` | Routing decisions |
| `GET /api/executions/{id}/compare?step_a=&step_b=` | Compare two steps |
| `WS /ws/live` | Live execution updates |

The server also serves the built frontend as static files.

### 3.8 Frontend Visualizer (`frontend/`)

React + TypeScript + Tailwind CSS. Dark theme designed for developer tools.

Components:
- **ExecutionList** — sidebar listing all recorded executions
- **Timeline** — horizontal node chain: [Start] → planner → searcher → [End]
- **ReplaySlider** — scrub through execution timeline
- **DiffViewer** — shows changed/added/removed with color coding
- **JsonViewer** — collapsible JSON explorer with change highlighting
- **RoutingInspector** — displays conditional edge evaluations

Keyboard shortcuts: Arrow keys / j/k for step navigation, 1/2/3 for tabs.

## 4. Data Flow

```
1. User calls app.invoke(initial_state)
2. LangGraph starts executing nodes
3. For each node:
   a. Wrapper captures state_before (deep copy)
   b. Node executes normally
   c. Wrapper computes state_after (merge)
   d. Collector serializes both states
   e. Diff engine computes structural diff
   f. Storage persists step (checkpoint or diff-only)
   g. WebSocket broadcast to connected UIs
4. Execution ends, final state recorded
5. UI fetches data via REST API
6. Replay engine reconstructs any requested state
```

## 5. Performance Considerations

### Storage efficiency
- Full state snapshots only every N steps (configurable, default 10)
- Non-checkpoint steps store only the diff (typically 10-100x smaller)
- For a 50-step execution with 10KB average state: ~55KB vs ~500KB naive approach

### Runtime overhead
- Deep copy: ~0.1ms for typical state (< 100 keys)
- Serialization: ~0.1ms
- Diff computation: ~0.05ms
- SQLite write: ~1ms (WAL mode, async)
- **Total per-step overhead: ~1.5ms** — negligible vs LLM call latency (100ms-10s)

### Memory
- State copies are released after persistence
- No accumulation in memory across steps

### What to avoid
- Logging every field of every state (use diffs)
- Synchronous storage writes blocking node execution
- Large binary blobs in state (truncated by serializer)

## 6. Extensibility Strategy

### New framework adapters
```python
class CrewAIAdapter(FrameworkAdapter):
    @property
    def framework_name(self) -> str:
        return "CrewAI"

    def instrument(self, crew):
        # Wrap crew's task execution
        ...
```

### New storage backends
```python
class PostgreSQLStorage(StorageBackend):
    async def save_step(self, step):
        # Write to PostgreSQL
        ...
```

### Custom diff strategies
The diff engine is a pure function. Replace it by passing a custom differ
to the collector.

### Plugin hooks
Future: pre/post step hooks for custom instrumentation (e.g., token counting,
latency measurement).

## 7. Directory Structure

```
state-of-mind/
├── src/lgdebug/
│   ├── __init__.py              # Public API: enable_debugging, DebugConfig
│   ├── core/
│   │   ├── config.py            # DebugConfig dataclass
│   │   ├── models.py            # Execution, ExecutionStep, StateDiff, RoutingDecision
│   │   ├── diff.py              # Structural diff engine + apply_diff
│   │   ├── serialization.py     # Safe serialization for arbitrary Python objects
│   │   └── collector.py         # Central event coordinator
│   ├── adapters/
│   │   ├── base.py              # FrameworkAdapter ABC
│   │   └── langgraph.py         # LangGraph-specific instrumentation
│   ├── storage/
│   │   ├── base.py              # StorageBackend ABC
│   │   └── sqlite.py            # SQLite implementation with checkpoint strategy
│   ├── replay/
│   │   └── engine.py            # Deterministic state reconstruction
│   ├── server/
│   │   └── app.py               # FastAPI debug server
│   └── cli/
│       └── main.py              # lgdebug CLI entry point
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # Root application
│   │   ├── main.tsx             # Entry point
│   │   ├── index.css            # Tailwind + custom styles
│   │   ├── components/
│   │   │   ├── Timeline.tsx     # Execution timeline
│   │   │   ├── ExecutionList.tsx # Sidebar execution list
│   │   │   ├── ExecutionView.tsx # Main detail view
│   │   │   ├── DiffViewer.tsx   # Structural diff display
│   │   │   ├── JsonViewer.tsx   # Collapsible JSON explorer
│   │   │   ├── ReplaySlider.tsx # Step scrubbing slider
│   │   │   └── RoutingInspector.tsx # Routing decision display
│   │   ├── hooks/
│   │   │   └── useWebSocket.ts  # Live update hook
│   │   ├── lib/
│   │   │   └── api.ts           # Backend API client
│   │   └── types/
│   │       └── index.ts         # TypeScript type definitions
│   └── [vite/tailwind config]
├── tests/
│   ├── unit/
│   │   ├── test_diff.py         # 14 tests
│   │   ├── test_serialization.py # 14 tests
│   │   └── test_storage.py      # 4 tests
│   └── integration/
│       └── test_collector.py    # 2 end-to-end tests
├── examples/
│   └── research_agent.py        # Full LangGraph integration example
├── pyproject.toml               # Package configuration
└── README.md
```

## 8. Future Roadmap

1. **Execution comparison** — diff two complete runs side by side
2. **Time-travel debugging** — re-execute from any step with modified state
3. **Token usage overlay** — show LLM costs per node in the timeline
4. **Export/import** — share execution traces as portable files
5. **VS Code extension** — embedded debugger panel
6. **Streaming support** — handle streaming LLM responses
7. **Multi-agent** — visualize parallel agent interactions
8. **CrewAI adapter** — second framework integration
9. **OpenAI Agents SDK adapter** — third framework integration
10. **Remote mode** — team sharing of execution traces
