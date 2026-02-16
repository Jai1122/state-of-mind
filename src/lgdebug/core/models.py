"""Domain models for execution traces and state snapshots.

These are plain data containers — no business logic. Every component in the
system reads and writes these structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class StepStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StateDiff:
    """Structured diff between two state snapshots.

    Each entry in `changed`, `added`, `removed` is a dict with:
        path: dotted key path  (e.g. "messages.2.content")
        old_value / new_value: the values (only the relevant one for add/remove)
    """

    changed: list[dict[str, Any]] = field(default_factory=list)
    added: list[dict[str, Any]] = field(default_factory=list)
    removed: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.changed or self.added or self.removed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "added": self.added,
            "removed": self.removed,
        }


@dataclass
class ExecutionStep:
    """One node execution within a graph run."""

    step_id: str = field(default_factory=lambda: uuid4().hex[:12])
    execution_id: str = ""
    node_name: str = ""
    step_index: int = 0
    timestamp_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    timestamp_end: datetime | None = None
    status: StepStatus = StepStatus.RUNNING
    state_before: dict[str, Any] | None = None  # populated on checkpoint steps
    state_after: dict[str, Any] | None = None  # populated on checkpoint steps
    state_diff: StateDiff = field(default_factory=StateDiff)
    is_checkpoint: bool = False
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "execution_id": self.execution_id,
            "node_name": self.node_name,
            "step_index": self.step_index,
            "timestamp_start": self.timestamp_start.isoformat(),
            "timestamp_end": self.timestamp_end.isoformat() if self.timestamp_end else None,
            "status": self.status.value,
            "state_before": self.state_before,
            "state_after": self.state_after,
            "state_diff": self.state_diff.to_dict(),
            "is_checkpoint": self.is_checkpoint,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class RoutingDecision:
    """Captured conditional edge evaluation."""

    step_id: str = ""
    source_node: str = ""
    target_node: str = ""
    condition_description: str = ""  # human-readable representation
    condition_inputs: dict[str, Any] = field(default_factory=dict)
    evaluated_value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "source_node": self.source_node,
            "target_node": self.target_node,
            "condition_description": self.condition_description,
            "condition_inputs": self.condition_inputs,
            "evaluated_value": self.evaluated_value,
        }


@dataclass
class Execution:
    """A single graph run from start to end."""

    execution_id: str = field(default_factory=lambda: uuid4().hex[:16])
    graph_name: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    status: StepStatus = StepStatus.RUNNING
    initial_state: dict[str, Any] = field(default_factory=dict)
    final_state: dict[str, Any] | None = None
    step_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "graph_name": self.graph_name,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "status": self.status.value,
            "initial_state": self.initial_state,
            "final_state": self.final_state,
            "step_count": self.step_count,
            "metadata": self.metadata,
        }
