"""Tests for the SQLite storage backend."""

import tempfile
from pathlib import Path

import pytest

from lgdebug.core.diff import compute_diff
from lgdebug.core.models import Execution, ExecutionStep, StepStatus
from lgdebug.storage.sqlite import SQLiteStorage


@pytest.fixture
async def storage():
    """Create a temporary SQLite storage instance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SQLiteStorage(db_path)
        await store.initialize()
        yield store
        await store.close()


class TestSQLiteStorage:
    @pytest.mark.asyncio
    async def test_save_and_get_execution(self, storage: SQLiteStorage):
        execution = Execution(
            execution_id="test_001",
            graph_name="test_graph",
            initial_state={"query": "hello"},
        )
        await storage.save_execution(execution)

        loaded = await storage.get_execution("test_001")
        assert loaded is not None
        assert loaded.execution_id == "test_001"
        assert loaded.graph_name == "test_graph"
        assert loaded.initial_state == {"query": "hello"}

    @pytest.mark.asyncio
    async def test_list_executions(self, storage: SQLiteStorage):
        for i in range(3):
            await storage.save_execution(
                Execution(execution_id=f"exec_{i}", graph_name="test")
            )

        results = await storage.list_executions()
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_save_and_get_step(self, storage: SQLiteStorage):
        execution = Execution(execution_id="e1", graph_name="test")
        await storage.save_execution(execution)

        diff = compute_diff({"a": 1}, {"a": 2})
        step = ExecutionStep(
            step_id="s1",
            execution_id="e1",
            node_name="planner",
            step_index=0,
            state_before={"a": 1},
            state_after={"a": 2},
            state_diff=diff,
            is_checkpoint=True,
            status=StepStatus.COMPLETED,
        )
        await storage.save_step(step)

        loaded = await storage.get_step("s1")
        assert loaded is not None
        assert loaded.node_name == "planner"
        assert loaded.state_after == {"a": 2}
        assert loaded.is_checkpoint is True

    @pytest.mark.asyncio
    async def test_state_reconstruction(self, storage: SQLiteStorage):
        """Test that get_state_at_step correctly reconstructs from checkpoint + diffs."""
        execution = Execution(
            execution_id="e1",
            graph_name="test",
            initial_state={"x": 0},
        )
        await storage.save_execution(execution)

        # Step 0: checkpoint with full state.
        s0_before = {"x": 0}
        s0_after = {"x": 1, "y": "new"}
        diff0 = compute_diff(s0_before, s0_after)
        await storage.save_step(
            ExecutionStep(
                step_id="s0",
                execution_id="e1",
                node_name="node_a",
                step_index=0,
                state_before=s0_before,
                state_after=s0_after,
                state_diff=diff0,
                is_checkpoint=True,
                status=StepStatus.COMPLETED,
            )
        )

        # Step 1: diff-only (not a checkpoint).
        s1_before = s0_after
        s1_after = {"x": 2, "y": "new", "z": True}
        diff1 = compute_diff(s1_before, s1_after)
        await storage.save_step(
            ExecutionStep(
                step_id="s1",
                execution_id="e1",
                node_name="node_b",
                step_index=1,
                state_diff=diff1,
                is_checkpoint=False,
                status=StepStatus.COMPLETED,
            )
        )

        # Reconstruct state at step 0 (checkpoint — direct).
        state_at_0 = await storage.get_state_at_step("e1", 0)
        assert state_at_0 == {"x": 1, "y": "new"}

        # Reconstruct state at step 1 (checkpoint + 1 diff).
        state_at_1 = await storage.get_state_at_step("e1", 1)
        assert state_at_1 == {"x": 2, "y": "new", "z": True}
