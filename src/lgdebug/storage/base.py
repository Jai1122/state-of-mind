"""Abstract storage interface.

All storage backends must implement this protocol. This allows swapping
SQLite for PostgreSQL, S3-backed, or in-memory stores without touching
the rest of the system.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from lgdebug.core.models import Execution, ExecutionStep, RoutingDecision


class StorageBackend(ABC):
    """Abstract base for execution trace storage."""

    @abstractmethod
    async def initialize(self) -> None:
        """Create tables / prepare the storage backend."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up connections."""
        ...

    # --- Executions ---

    @abstractmethod
    async def save_execution(self, execution: Execution) -> None:
        ...

    @abstractmethod
    async def update_execution(self, execution: Execution) -> None:
        ...

    @abstractmethod
    async def get_execution(self, execution_id: str) -> Execution | None:
        ...

    @abstractmethod
    async def list_executions(
        self, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        ...

    # --- Steps ---

    @abstractmethod
    async def save_step(self, step: ExecutionStep) -> None:
        ...

    @abstractmethod
    async def get_step(self, step_id: str) -> ExecutionStep | None:
        ...

    @abstractmethod
    async def list_steps(self, execution_id: str) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def get_state_at_step(
        self, execution_id: str, step_index: int
    ) -> dict[str, Any] | None:
        """Reconstruct full state at a given step index.

        For checkpoint steps, returns stored state_after directly.
        For non-checkpoint steps, reconstructs from nearest prior checkpoint + diffs.
        """
        ...

    # --- Routing ---

    @abstractmethod
    async def save_routing_decision(self, decision: RoutingDecision) -> None:
        ...

    @abstractmethod
    async def get_routing_decisions(self, execution_id: str) -> list[dict[str, Any]]:
        ...
