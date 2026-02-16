# lgdebug — LangGraph State Debugger

> Redux DevTools for LangGraph Agents

A developer tool for debugging state evolution in LangGraph-based AI systems.
Visualize how state changes across nodes, inspect diffs, and replay executions.

## Quick Start

```bash
pip install lgdebug

# In your LangGraph app:
from lgdebug import enable_debugging
graph = enable_debugging(graph)

# Start the debugger UI:
lgdebug run
```

## Features

- Execution timeline visualization
- State before/after inspection for each node
- Structural diff viewer — see only what changed
- Routing decision inspector
- Replay mode — scrub through execution without re-running
- Zero node modification required
- Local-first — no SaaS dependency

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
