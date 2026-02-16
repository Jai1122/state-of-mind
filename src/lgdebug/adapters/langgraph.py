"""LangGraph adapter — zero-modification state debugging instrumentation.

Integration strategy:
    LangGraph's StateGraph compiles into a CompiledGraph (or Pregel) that
    has a `.nodes` dict mapping node names to RunnableCallable objects.
    Each node is a function: (state) -> partial_state_update.

    We wrap each node's underlying callable so that:
    1. We capture a deep copy of the state BEFORE the node runs.
    2. We let the node run normally.
    3. We capture the state AFTER (by merging the node's return into before).
    4. We send (before, after) to the collector.

    For conditional edges, we wrap the condition functions similarly.

    This approach requires ZERO changes to user node code. The developer
    simply calls enable_debugging(graph) before graph.compile().

Usage:
    from lgdebug import enable_debugging

    graph = StateGraph(MyState)
    graph.add_node("planner", planner_fn)
    graph.add_edge("planner", "executor")

    # One line to enable debugging:
    graph = enable_debugging(graph)

    app = graph.compile()
    result = app.invoke({"query": "hello"})
"""

from __future__ import annotations

import functools
import inspect
import logging
from typing import Any
from uuid import uuid4

from lgdebug.adapters.base import FrameworkAdapter
from lgdebug.core.collector import DebugCollector, get_collector, set_collector
from lgdebug.core.config import DebugConfig
from lgdebug.core.serialization import safe_deepcopy, serialize_state
from lgdebug.storage.sqlite_sync import SyncSQLiteStorage

logger = logging.getLogger("lgdebug.langgraph")


class LangGraphAdapter(FrameworkAdapter):
    """Instruments a LangGraph StateGraph for state debugging."""

    @property
    def framework_name(self) -> str:
        return "LangGraph"

    def instrument(self, graph: Any) -> Any:
        """Wrap all nodes in the graph with state capture.

        Works with both StateGraph (pre-compile) and CompiledStateGraph (post-compile).
        Returns the same object type.
        """
        # Handle pre-compiled StateGraph.
        if hasattr(graph, "nodes") and hasattr(graph, "add_node"):
            return self._instrument_state_graph(graph)

        # Handle compiled graph (Pregel / CompiledStateGraph).
        if hasattr(graph, "nodes") and hasattr(graph, "invoke"):
            return self._instrument_compiled_graph(graph)

        raise TypeError(
            f"Cannot instrument {type(graph).__name__}. "
            "Expected a LangGraph StateGraph or CompiledStateGraph."
        )

    def _instrument_state_graph(self, graph: Any) -> Any:
        """Wrap nodes in an uncompiled StateGraph.

        LangGraph 1.0.x internal structure:
            graph.nodes: dict[str, StateNodeSpec]
            StateNodeSpec.runnable: RunnableCallable
            RunnableCallable.func: the original Python function

        We replace .func inside the RunnableCallable so LangGraph's
        execution engine (which expects RunnableCallable objects) is unaffected.

            graph.branches: defaultdict(dict) mapping
                source_node -> {router_name -> BranchSpec}
            BranchSpec.path: RunnableCallable wrapping the router function
        """
        node_count = 0
        for name, node_spec in graph.nodes.items():
            if name in ("__start__", "__end__"):
                continue

            # StateNodeSpec → RunnableCallable → func
            runnable = getattr(node_spec, "runnable", None)
            if runnable is not None and hasattr(runnable, "func"):
                original_func = runnable.func
                runnable.func = _wrap_node_function(name, original_func, self.config)
                # Also wrap the async variant if present.
                if hasattr(runnable, "afunc") and runnable.afunc is not None:
                    runnable.afunc = _wrap_node_function(name, runnable.afunc, self.config)
                node_count += 1
            elif callable(node_spec):
                # Fallback for older LangGraph versions where nodes are plain callables.
                graph.nodes[name] = _wrap_node_function(name, node_spec, self.config)
                node_count += 1

        # Wrap conditional edges (stored in graph.branches in LangGraph 1.0.x).
        branches = getattr(graph, "branches", None)
        if branches:
            for source_node, branch_map in branches.items():
                for branch_name, branch_spec in branch_map.items():
                    path_runnable = getattr(branch_spec, "path", None)
                    if path_runnable is not None and hasattr(path_runnable, "func"):
                        original_path = path_runnable.func
                        path_runnable.func = _wrap_conditional_edge(
                            source_node, original_path, self.config
                        )

        logger.info("Instrumented StateGraph with %d nodes", node_count)
        return graph

    def _instrument_compiled_graph(self, graph: Any) -> Any:
        """Wrap nodes in an already-compiled graph.

        CompiledStateGraph.nodes is a dict of name -> PregelNode.
        PregelNode wraps a RunnableCallable which has .func/.afunc.
        """
        node_count = 0
        for name, node in graph.nodes.items():
            if name in ("__start__", "__end__"):
                continue
            # PregelNode → .bound (RunnableCallable) → .func
            bound = getattr(node, "bound", None)
            if bound is not None and hasattr(bound, "func"):
                bound.func = _wrap_node_function(name, bound.func, self.config)
                if hasattr(bound, "afunc") and bound.afunc is not None:
                    bound.afunc = _wrap_node_function(name, bound.afunc, self.config)
                node_count += 1
            elif callable(node):
                graph.nodes[name] = _wrap_node_function(name, node, self.config)
                node_count += 1

        logger.info("Instrumented CompiledGraph with %d nodes", node_count)
        return graph


def _wrap_node_function(node_name: str, fn: Any, config: DebugConfig) -> Any:
    """Create a wrapper that captures state before/after node execution.

    The wrapper must match the original function's sync/async nature so
    LangGraph's execution engine doesn't break.

    All collector calls are synchronous — no event loop manipulation.
    """
    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(state: Any, *args: Any, **kwargs: Any) -> Any:
            collector = get_collector()
            if collector is None or not config.enabled:
                return await fn(state, *args, **kwargs)

            state_before = safe_deepcopy(state)
            execution_id = _get_or_create_execution_id(state, kwargs)

            try:
                result = await fn(state, *args, **kwargs)
                state_after = _compute_state_after(state_before, result)
                # Collector is synchronous — safe to call from any context.
                collector.record_step(
                    execution_id=execution_id,
                    node_name=node_name,
                    state_before=state_before,
                    state_after=state_after,
                )
                return result
            except Exception as exc:
                collector.record_step(
                    execution_id=execution_id,
                    node_name=node_name,
                    state_before=state_before,
                    state_after=state_before,
                    error=str(exc),
                )
                raise

        return async_wrapper
    else:

        @functools.wraps(fn)
        def sync_wrapper(state: Any, *args: Any, **kwargs: Any) -> Any:
            collector = get_collector()
            if collector is None or not config.enabled:
                return fn(state, *args, **kwargs)

            state_before = safe_deepcopy(state)
            execution_id = _get_or_create_execution_id(state, kwargs)

            try:
                result = fn(state, *args, **kwargs)
                state_after = _compute_state_after(state_before, result)
                collector.record_step(
                    execution_id=execution_id,
                    node_name=node_name,
                    state_before=state_before,
                    state_after=state_after,
                )
                return result
            except Exception as exc:
                collector.record_step(
                    execution_id=execution_id,
                    node_name=node_name,
                    state_before=state_before,
                    state_after=state_before,
                    error=str(exc),
                )
                raise

        return sync_wrapper


def _wrap_conditional_edge(
    edge_key: str, condition_fn: Any, config: DebugConfig
) -> Any:
    """Wrap a conditional edge function to capture routing decisions."""

    @functools.wraps(condition_fn)
    def wrapper(state: Any) -> Any:
        collector = get_collector()
        result = condition_fn(state)

        if collector is not None and config.enabled:
            try:
                condition_inputs = serialize_state(state)
                collector.record_routing(
                    step_id="",
                    source_node=str(edge_key),
                    target_node=str(result),
                    condition_description=_get_function_description(condition_fn),
                    condition_inputs=condition_inputs,
                    evaluated_value=result,
                )
            except Exception:
                logger.debug("Failed to record routing decision", exc_info=True)

        return result

    return wrapper


def _get_function_description(fn: Any) -> str:
    """Extract a human-readable description of a condition function."""
    if hasattr(fn, "__name__"):
        name = fn.__name__
    elif hasattr(fn, "__class__"):
        name = fn.__class__.__name__
    else:
        name = str(fn)

    # Try to get the source for short functions.
    try:
        source = inspect.getsource(fn)
        lines = [l.strip() for l in source.splitlines() if l.strip() and not l.strip().startswith("#")]
        if len(lines) <= 5:
            return " | ".join(lines)
    except (OSError, TypeError):
        pass

    return name


def _compute_state_after(state_before: Any, node_result: Any) -> Any:
    """Merge a node's return value into the pre-execution state.

    LangGraph nodes return partial state updates (a dict). The graph engine
    merges these into the full state. We simulate this merge for capture.
    """
    if node_result is None:
        return state_before

    if isinstance(state_before, dict) and isinstance(node_result, dict):
        merged = dict(state_before)
        for key, value in node_result.items():
            # LangGraph uses Annotated types for list accumulation.
            # For simple debugging, we use the latest value.
            # The actual merged state will be captured on the next step's state_before.
            merged[key] = value
        return merged

    # If state is not a dict (unusual), return the result as-is.
    return node_result


def _get_or_create_execution_id(state: Any, kwargs: dict[str, Any]) -> str:
    """Extract or create an execution ID.

    LangGraph passes config through kwargs. We look for our execution_id there,
    or fall back to a thread-local / contextvar-based ID.
    """
    # Check if we injected the execution ID into config.
    config = kwargs.get("config", {})
    if isinstance(config, dict):
        exec_id = config.get("configurable", {}).get("lgdebug_execution_id")
        if exec_id:
            return exec_id

    # Check state for our tracking key.
    if isinstance(state, dict) and "__lgdebug_execution_id" in state:
        return state["__lgdebug_execution_id"]

    # Fall back to the module-level tracker.
    return _execution_tracker.get_current()


class _ExecutionTracker:
    """Simple execution ID tracker using contextvars for async safety."""

    def __init__(self) -> None:
        import contextvars
        self._var: contextvars.ContextVar[str] = contextvars.ContextVar(
            "lgdebug_execution_id", default=""
        )

    def set_current(self, execution_id: str) -> None:
        self._var.set(execution_id)

    def get_current(self) -> str:
        val = self._var.get()
        if not val:
            val = uuid4().hex[:16]
            self._var.set(val)
        return val


_execution_tracker = _ExecutionTracker()


# --- Public API ---


def enable_debugging(
    graph: Any,
    *,
    config: DebugConfig | None = None,
) -> Any:
    """Instrument a LangGraph graph for state debugging.

    This is the primary public API. Call it on your graph before or after
    compilation:

        graph = enable_debugging(graph)
        app = graph.compile()
        result = app.invoke(initial_state)

    Or on an already-compiled graph:

        app = graph.compile()
        app = enable_debugging(app)
        result = app.invoke(initial_state)

    Args:
        graph: A LangGraph StateGraph or CompiledStateGraph.
        config: Optional debug configuration. Uses defaults if not provided.

    Returns:
        The same graph object, now instrumented.
    """
    if config is None:
        config = DebugConfig()

    if not config.enabled:
        return graph

    # Initialize storage and collector if not already done.
    # Fully synchronous — no event loop manipulation.
    collector = get_collector()
    if collector is None:
        storage = SyncSQLiteStorage(config.db_path)
        storage.initialize()
        collector = DebugCollector(config, storage)
        set_collector(collector)
        logger.info("Debug collector initialized (db=%s)", config.db_path)

    adapter = LangGraphAdapter(config)
    return adapter.instrument(graph)
