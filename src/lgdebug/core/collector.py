"""Central collector that receives execution events from adapters.

The collector is the bridge between the instrumentation layer and storage.
It handles:
- Creating execution records
- Recording step transitions
- Computing diffs
- Deciding when to checkpoint (full snapshot vs diff-only)

IMPORTANT: This collector is fully synchronous. LangGraph runs sync node
functions inside its own async event loop, so any use of asyncio.run() or
event loop manipulation here causes deadlocks. All storage operations use
the synchronous sqlite3 backend.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from lgdebug.core.config import DebugConfig
from lgdebug.core.diff import compute_diff
from lgdebug.core.models import (
    Execution,
    ExecutionStep,
    RoutingDecision,
    StepStatus,
)
from lgdebug.core.serialization import safe_deepcopy, serialize_state
from lgdebug.storage.sqlite_sync import SyncSQLiteStorage

logger = logging.getLogger("lgdebug.collector")


class DebugCollector:
    """Receives execution events and persists them. Fully synchronous."""

    def __init__(self, config: DebugConfig, storage: SyncSQLiteStorage) -> None:
        self.config = config
        self.storage = storage
        self._lock = threading.Lock()
        self._step_counters: dict[str, int] = {}

    # --- Execution lifecycle ---

    def start_execution(
        self,
        execution_id: str,
        graph_name: str,
        initial_state: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> Execution:
        serialized = serialize_state(initial_state)
        execution = Execution(
            execution_id=execution_id,
            graph_name=graph_name,
            initial_state=serialized,
            metadata=metadata or {},
        )
        with self._lock:
            self._step_counters[execution_id] = 0
        self.storage.save_execution(execution)
        logger.debug("Execution started: %s (%s)", execution_id, graph_name)
        return execution

    def end_execution(
        self,
        execution_id: str,
        final_state: dict[str, Any],
        *,
        status: StepStatus = StepStatus.COMPLETED,
    ) -> None:
        execution = self.storage.get_execution(execution_id)
        if execution is None:
            logger.warning("end_execution called for unknown execution: %s", execution_id)
            return

        execution.ended_at = datetime.now(timezone.utc)
        execution.status = status
        execution.final_state = serialize_state(final_state)
        with self._lock:
            execution.step_count = self._step_counters.get(execution_id, 0)
        self.storage.update_execution(execution)
        logger.debug("Execution ended: %s (%s)", execution_id, status.value)

    # --- Step lifecycle ---

    def record_step(
        self,
        execution_id: str,
        node_name: str,
        state_before: dict[str, Any],
        state_after: dict[str, Any],
        *,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionStep:
        before_serialized = serialize_state(safe_deepcopy(state_before))
        after_serialized = serialize_state(safe_deepcopy(state_after))

        diff = compute_diff(
            before_serialized, after_serialized, ignore_keys=self.config.ignore_keys
        )

        with self._lock:
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

        self.storage.save_step(step)
        logger.debug(
            "Step %d: %s (checkpoint=%s, diff_size=%d)",
            step_index,
            node_name,
            is_checkpoint,
            len(diff.changed) + len(diff.added) + len(diff.removed),
        )
        return step

    def record_routing(
        self,
        step_id: str,
        source_node: str,
        target_node: str,
        condition_description: str,
        condition_inputs: dict[str, Any],
        evaluated_value: Any,
    ) -> None:
        decision = RoutingDecision(
            step_id=step_id,
            source_node=source_node,
            target_node=target_node,
            condition_description=condition_description,
            condition_inputs=serialize_state(condition_inputs),
            evaluated_value=serialize_state(evaluated_value),
        )
        self.storage.save_routing_decision(decision)


# --- Module-level singleton management ---

_collector: DebugCollector | None = None


def get_collector() -> DebugCollector | None:
    return _collector


def set_collector(collector: DebugCollector) -> None:
    global _collector
    _collector = collector
