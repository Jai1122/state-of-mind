"""Replay engine — deterministic state reconstruction without re-execution.

The replay engine reconstructs the full state at any point in an execution
timeline by combining checkpoint snapshots with incremental diffs.

Algorithm:
    1. Find the nearest checkpoint at or before the target step.
    2. Load the checkpoint's full state_after snapshot.
    3. Apply diffs from (checkpoint + 1) through the target step.

This approach balances storage cost (checkpoints are large) against
reconstruction cost (too few checkpoints means many diffs to apply).

The default checkpoint_interval of 10 means at most 9 diffs need to be
applied for any reconstruction — O(1) lookups in practice.

The replay engine also supports:
    - Full timeline reconstruction (all states for an execution)
    - State-at-step queries
    - Step range queries (for slider scrubbing in the UI)
"""

from __future__ import annotations

from typing import Any

from lgdebug.core.diff import apply_diff
from lgdebug.core.models import StateDiff
from lgdebug.storage.base import StorageBackend


class ReplayEngine:
    """Reconstructs state at any point in an execution timeline."""

    def __init__(self, storage: StorageBackend) -> None:
        self._storage = storage

    async def get_state_at_step(
        self, execution_id: str, step_index: int
    ) -> dict[str, Any] | None:
        """Reconstruct the state after a specific step executed.

        Delegates to the storage backend which handles the
        checkpoint + diff reconstruction internally.
        """
        return await self._storage.get_state_at_step(execution_id, step_index)

    async def get_full_timeline(
        self, execution_id: str
    ) -> list[dict[str, Any]]:
        """Reconstruct complete state timeline for an execution.

        Returns a list of dicts, one per step:
            {
                "step_index": int,
                "node_name": str,
                "state": dict,  # full reconstructed state
                "diff": StateDiff dict,
            }

        This is used by the UI's replay slider to enable instant scrubbing
        through the execution timeline.
        """
        execution = await self._storage.get_execution(execution_id)
        if execution is None:
            return []

        steps = await self._storage.list_steps(execution_id)
        if not steps:
            return []

        timeline: list[dict[str, Any]] = []
        current_state = execution.initial_state

        for step_data in steps:
            diff = StateDiff(
                changed=step_data["state_diff"].get("changed", []),
                added=step_data["state_diff"].get("added", []),
                removed=step_data["state_diff"].get("removed", []),
            )

            # If this is a checkpoint with full state, use it directly.
            if step_data.get("is_checkpoint") and step_data.get("state_after"):
                current_state = step_data["state_after"]
            else:
                current_state = apply_diff(current_state, diff)

            timeline.append({
                "step_index": step_data["step_index"],
                "node_name": step_data["node_name"],
                "state": current_state,
                "diff": step_data["state_diff"],
                "timestamp_start": step_data["timestamp_start"],
                "timestamp_end": step_data["timestamp_end"],
                "status": step_data["status"],
                "error": step_data.get("error"),
            })

        return timeline

    async def get_state_range(
        self, execution_id: str, start_step: int, end_step: int
    ) -> list[dict[str, Any]]:
        """Reconstruct states for a range of steps.

        Used for smooth slider scrubbing — the UI pre-fetches a window
        of states around the current position.
        """
        timeline = await self.get_full_timeline(execution_id)
        return [
            entry
            for entry in timeline
            if start_step <= entry["step_index"] <= end_step
        ]

    async def compare_steps(
        self, execution_id: str, step_a: int, step_b: int
    ) -> dict[str, Any]:
        """Compare states at two arbitrary steps.

        Useful for "what changed between step 3 and step 7?" queries.
        """
        from lgdebug.core.diff import compute_diff

        state_a = await self.get_state_at_step(execution_id, step_a)
        state_b = await self.get_state_at_step(execution_id, step_b)

        if state_a is None or state_b is None:
            return {"error": "One or both steps not found"}

        diff = compute_diff(state_a, state_b)
        return {
            "step_a": step_a,
            "step_b": step_b,
            "state_a": state_a,
            "state_b": state_b,
            "diff": diff.to_dict(),
        }
