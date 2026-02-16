"""Example: LangGraph research agent with lgdebug instrumentation.

This demonstrates how to add state debugging to a LangGraph application
with a single function call — zero node modifications required.

Run:
    # Terminal 1: Start the debug server
    lgdebug run

    # Terminal 2: Run this example
    python examples/research_agent.py

    # Open http://localhost:6274 to see the execution in the debugger.

Requirements:
    pip install lgdebug[langgraph]
"""

from __future__ import annotations

import asyncio
from typing import Annotated, TypedDict

# --- State definition ---


class ResearchState(TypedDict, total=False):
    """State for the research agent graph."""

    query: str
    intent: str
    search_results: list[dict[str, str]]
    summary: str
    messages: Annotated[list[dict[str, str]], lambda a, b: a + b]
    step_count: int


# --- Node functions (these are NEVER modified for debugging) ---


def planner(state: ResearchState) -> ResearchState:
    """Analyze the query and determine intent."""
    query = state.get("query", "")

    # Simulate LLM planning.
    if "compare" in query.lower():
        intent = "compare"
    elif "summarize" in query.lower() or "summary" in query.lower():
        intent = "summarize"
    else:
        intent = "research"

    return {
        "intent": intent,
        "messages": [{"role": "assistant", "content": f"Intent classified as: {intent}"}],
        "step_count": state.get("step_count", 0) + 1,
    }


def searcher(state: ResearchState) -> ResearchState:
    """Perform search based on query."""
    query = state.get("query", "")

    # Simulate search results.
    results = [
        {"title": f"Result 1 for '{query}'", "snippet": "This is the first result..."},
        {"title": f"Result 2 for '{query}'", "snippet": "Another relevant finding..."},
        {"title": f"Result 3 for '{query}'", "snippet": "Additional context here..."},
    ]

    return {
        "search_results": results,
        "messages": [{"role": "tool", "content": f"Found {len(results)} results"}],
        "step_count": state.get("step_count", 0) + 1,
    }


def summarizer(state: ResearchState) -> ResearchState:
    """Summarize the search results."""
    results = state.get("search_results", [])
    n = len(results)

    summary = f"Based on {n} sources, the answer to '{state.get('query', '')}' is: [simulated summary of findings]."

    return {
        "summary": summary,
        "messages": [{"role": "assistant", "content": summary}],
        "step_count": state.get("step_count", 0) + 1,
    }


def router(state: ResearchState) -> str:
    """Route based on intent."""
    intent = state.get("intent", "research")
    if intent == "summarize":
        return "summarizer"
    return "searcher"


# --- Graph construction ---


def build_graph():
    """Build the research agent graph.

    This function shows the ONLY integration point: enable_debugging().
    """
    try:
        from langgraph.graph import StateGraph, END
    except ImportError:
        print("LangGraph not installed. Install with: pip install langgraph")
        print("Running in simulation mode instead...\n")
        return None

    from lgdebug import enable_debugging

    graph = StateGraph(ResearchState)

    # Add nodes.
    graph.add_node("planner", planner)
    graph.add_node("searcher", searcher)
    graph.add_node("summarizer", summarizer)

    # Add edges.
    graph.set_entry_point("planner")
    graph.add_conditional_edges("planner", router, {"searcher": "searcher", "summarizer": "summarizer"})
    graph.add_edge("searcher", "summarizer")
    graph.add_edge("summarizer", END)

    # ONE LINE to enable debugging — no node changes needed.
    graph = enable_debugging(graph)

    return graph.compile()


# --- Simulation mode (runs without LangGraph installed) ---


async def simulate_execution():
    """Demonstrate the debugger using direct collector calls.

    This is useful for testing the debugger UI without installing LangGraph.
    """
    from lgdebug.core.collector import DebugCollector, set_collector
    from lgdebug.core.config import DebugConfig
    from lgdebug.storage.sqlite import SQLiteStorage

    config = DebugConfig()
    storage = SQLiteStorage(config.db_path)
    await storage.initialize()

    collector = DebugCollector(config, storage)
    set_collector(collector)

    # Simulate a full execution.
    initial_state: dict = {"query": "What is LangGraph?", "messages": [], "step_count": 0}
    execution = await collector.start_execution(
        execution_id="sim_001",
        graph_name="research_agent",
        initial_state=initial_state,
    )

    # Step 1: planner
    state_after_planner = {
        **initial_state,
        "intent": "research",
        "messages": [{"role": "assistant", "content": "Intent classified as: research"}],
        "step_count": 1,
    }
    await collector.record_step(
        execution_id=execution.execution_id,
        node_name="planner",
        state_before=initial_state,
        state_after=state_after_planner,
    )

    # Step 2: searcher
    state_after_search = {
        **state_after_planner,
        "search_results": [
            {"title": "LangGraph overview", "snippet": "LangGraph is a library for building..."},
            {"title": "LangGraph vs LangChain", "snippet": "While LangChain provides..."},
            {"title": "State machines in AI", "snippet": "Graph-based execution allows..."},
        ],
        "messages": [
            *state_after_planner["messages"],
            {"role": "tool", "content": "Found 3 results"},
        ],
        "step_count": 2,
    }
    await collector.record_step(
        execution_id=execution.execution_id,
        node_name="searcher",
        state_before=state_after_planner,
        state_after=state_after_search,
    )

    # Step 3: summarizer
    state_after_summary = {
        **state_after_search,
        "summary": "LangGraph is a library for building stateful AI agents using graph-based execution.",
        "messages": [
            *state_after_search["messages"],
            {
                "role": "assistant",
                "content": "LangGraph is a library for building stateful AI agents using graph-based execution.",
            },
        ],
        "step_count": 3,
    }
    await collector.record_step(
        execution_id=execution.execution_id,
        node_name="summarizer",
        state_before=state_after_search,
        state_after=state_after_summary,
    )

    # End execution.
    await collector.end_execution(
        execution_id=execution.execution_id,
        final_state=state_after_summary,
    )

    await storage.close()
    print(f"Simulated execution '{execution.execution_id}' recorded.")
    print("Run 'lgdebug run' to view in the debugger UI.")


# --- Main ---


def main():
    """Run the example."""
    app = build_graph()

    if app is not None:
        # Real LangGraph execution.
        result = app.invoke({"query": "What is LangGraph?", "messages": [], "step_count": 0})
        print("Result:", result.get("summary", "No summary"))
    else:
        # Simulation mode.
        asyncio.run(simulate_execution())


if __name__ == "__main__":
    main()
