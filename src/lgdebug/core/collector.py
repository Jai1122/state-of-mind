"""Central collector that receives execution events from adapters.

The collector is the bridge between the instrumentation layer and storage.
It handles:
- Creating execution records
- Recording step transitions
- Computing diffs
- Deciding when to checkpoint (full snapshot vs diff-only)
- Broadcasting events to the debug server for live updates

Thread safety: the collector uses asyncio locks. For sync adapters, events
are queued and processed on the event loop.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from lgdebug.core.config import DebugConfig
from lgdebug.core.diff import compute_diff
from lgdebug.core.models import (
    Execution,
    ExecutionStep,
    RoutingDecision,
    StepStatus,
)
from lgdebug.core.serialization import safe_deepcopy, serialize_state
from lgdebug.storage.base import StorageBackend

logger = logging.getLogger("lgdebug.collector")

# Type alias for event subscribers (e.g., WebSocket broadcaster).
EventCallback = Callable[[str, dict[str, Any]], Any]


class DebugCollector:
    """Receives execution events and persists them.

    Designed to be used as a singleton per process. Adapters obtain a reference
    to the collector and call its methods during graph execution.
    """

    def __init__(self, config: DebugConfig, storage: StorageBackend) -> None:
        self.config = config
        self.storage = storage
        self._subscribers: list[EventCallback] = []
        self._lock = asyncio.Lock()
        # Track current step counters per execution.
        self._step_counters: dict[str, int] = {}

    def subscribe(self, callback: EventCallback) -> None:
        """Register a callback for live event streaming."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: EventCallback) -> None:
        self._subscribers = [s for s in self._subscribers if s is not callback]

    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Notify all subscribers of an event."""
        for cb in self._subscribers:
            try:
                result = cb(event_type, data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.warning("Event subscriber error", exc_info=True)

    # --- Execution lifecycle ---

    async def start_execution(
        self,
        execution_id: str,
        graph_name: str,
        initial_state: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> Execution:
        """Record the start of a new graph execution."""
        serialized = serialize_state(initial_state)
        execution = Execution(
            execution_id=execution_id,
            graph_name=graph_name,
            initial_state=serialized,
            metadata=metadata or {},
        )
        async with self._lock:
            self._step_counters[execution_id] = 0
            await self.storage.save_execution(execution)

        await self._emit("execution_started", execution.to_dict())
        logger.debug("Execution started: %s (%s)", execution_id, graph_name)
        return execution

    async def end_execution(
        self,
        execution_id: str,
        final_state: dict[str, Any],
        *,
        status: StepStatus = StepStatus.COMPLETED,
        error: str | None = None,
    ) -> None:
        """Record the end of a graph execution."""
        execution = await self.storage.get_execution(execution_id)
        if execution is None:
            logger.warning("end_execution called for unknown execution: %s", execution_id)
            return

        execution.ended_at = datetime.now(timezone.utc)
        execution.status = status
        execution.final_state = serialize_state(final_state)
        async with self._lock:
            execution.step_count = self._step_counters.get(execution_id, 0)
        await self.storage.update_execution(execution)

        await self._emit("execution_ended", execution.to_dict())
        logger.debug("Execution ended: %s (%s)", execution_id, status.value)

    # --- Step lifecycle ---

    async def record_step(
        self,
        execution_id: str,
        node_name: str,
        state_before: dict[str, Any],
        state_after: dict[str, Any],
        *,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionStep:
        """Record a single node execution with state transition.

        This is the primary method called by adapters. It:
        1. Deep-copies and serializes both states.
        2. Computes the structural diff.
        3. Decides whether this step is a checkpoint.
        4. Persists the step.
        """
        # Serialize states.
        before_serialized = serialize_state(safe_deepcopy(state_before))
        after_serialized = serialize_state(safe_deepcopy(state_after))

        # Compute diff.
        diff = compute_diff(
            before_serialized, after_serialized, ignore_keys=self.config.ignore_keys
        )

        # Determine step index and checkpoint status.
        async with self._lock:
            step_index = self._step_counters.get(execution_id, 0)
            self._step_counters[execution_id] = step_index + 1

        is_checkpoint = (step_index % self.config.checkpoint_interval == 0) or step_index == 0
        now = datetime.now(timezone.utc)

        step = ExecutionStep(
            execution_id=execution_id,
            node_name=node_name,
            step_index=step_index,
            timestamp_start=now,
            timestamp_end=now,
            status=StepStatus.FAILED if error else StepStatus.COMPLETED,
            state_before=before_serialized if is_checkpoint else None,
            state_after=after_serialized if is_checkpoint else None,
            state_diff=diff,
            is_checkpoint=is_checkpoint,
            error=error,
            metadata=metadata or {},
        )

        await self.storage.save_step(step)
        await self._emit("step_recorded", step.to_dict())
        logger.debug(
            "Step %d: %s (checkpoint=%s, diff_size=%d)",
            step_index,
            node_name,
            is_checkpoint,
            len(diff.changed) + len(diff.added) + len(diff.removed),
        )
        return step

    async def record_routing(
        self,
        step_id: str,
        source_node: str,
        target_node: str,
        condition_description: str,
        condition_inputs: dict[str, Any],
        evaluated_value: Any,
    ) -> None:
        """Record a conditional routing decision."""
        decision = RoutingDecision(
            step_id=step_id,
            source_node=source_node,
            target_node=target_node,
            condition_description=condition_description,
            condition_inputs=serialize_state(condition_inputs),
            evaluated_value=serialize_state(evaluated_value),
        )
        await self.storage.save_routing_decision(decision)
        await self._emit("routing_decision", decision.to_dict())


# --- Module-level singleton management ---

_collector: DebugCollector | None = None


def get_collector() -> DebugCollector | None:
    """Return the active collector, if any."""
    return _collector


def set_collector(collector: DebugCollector) -> None:
    """Set the global collector instance."""
    global _collector
    _collector = collector
