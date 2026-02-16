"""Framework-agnostic adapter protocol.

Every framework adapter (LangGraph, CrewAI, OpenAI Agents, etc.) implements
this interface to translate framework-specific graph execution into our
universal ExecutionStep model.

The adapter is responsible for:
1. Intercepting node execution without requiring node code changes.
2. Capturing state_before and state_after for each node.
3. Emitting ExecutionStep records to the collector.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from lgdebug.core.config import DebugConfig


class FrameworkAdapter(ABC):
    """Base class for framework-specific debug adapters."""

    def __init__(self, config: DebugConfig) -> None:
        self.config = config

    @abstractmethod
    def instrument(self, graph: Any) -> Any:
        """Wrap the graph object with debugging instrumentation.

        Must return the same type of graph object so user code is unaffected.
        """
        ...

    @property
    @abstractmethod
    def framework_name(self) -> str:
        """Human-readable framework name for UI display."""
        ...
