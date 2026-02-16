"""lgdebug — State debugger and visualizer for LangGraph agents.

Usage:
    from lgdebug import enable_debugging
    graph = enable_debugging(graph)

    # Or via CLI:
    $ lgdebug run
"""

from lgdebug.adapters.langgraph import enable_debugging
from lgdebug.core.config import DebugConfig

__version__ = "0.1.0"
__all__ = ["enable_debugging", "DebugConfig"]
