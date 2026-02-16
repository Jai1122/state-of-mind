"""Integration test: collector → storage → replay pipeline."""

import tempfile
from pathlib import Path

from lgdebug.core.collector import DebugCollector
from lgdebug.core.config import DebugConfig
from lgdebug.storage.sqlite_sync import SyncSQLiteStorage


def _make_stack():
    """Create a full stack: config → storage → collector."""
    tmpdir = tempfile.mkdtemp()
    config = DebugConfig(
        db_path=Path(tmpdir) / "test.db",
        checkpoint_interval=2,  # checkpoint every 2 steps for testing
    )
    storage = SyncSQLiteStorage(config.db_path)
    storage.initialize()
    collector = DebugCollector(config, storage)
    return config, storage, collector


class TestFullPipeline:
    def test_record_and_replay(self):
        _, storage, collector = _make_stack()

        # Start execution.
        initial = {"query": "test", "count": 0}
        execution = collector.start_execution(
            execution_id="e1",
            graph_name="test_graph",
            initial_state=initial,
        )

        # Record 4 steps (checkpoints at 0, 2).
        states = [
            initial,
            {"query": "test", "count": 1, "intent": "a"},
            {"query": "test", "count": 2, "intent": "a", "result": "x"},
            {"query": "test", "count": 3, "intent": "b", "result": "x"},
            {"query": "test", "count": 4, "intent": "b", "result": "y", "done": True},
        ]

        for i in range(4):
            collector.record_step(
                execution_id="e1",
                node_name=f"node_{i}",
                state_before=states[i],
                state_after=states[i + 1],
            )

        # End execution.
        collector.end_execution(
            execution_id="e1",
            final_state=states[4],
        )

        # Verify execution was recorded.
        execution = storage.get_execution("e1")
        assert execution is not None
        assert execution.step_count == 4

        # Verify steps.
        steps = storage.list_steps("e1")
        assert len(steps) == 4
        assert steps[0]["node_name"] == "node_0"
        assert steps[3]["node_name"] == "node_3"

        # Verify state reconstruction at non-checkpoint step.
        state_at_3 = storage.get_state_at_step("e1", 3)
        assert state_at_3 is not None
        assert state_at_3["count"] == 4
        assert state_at_3["done"] is True

        storage.close()

    def test_compare_steps(self):
        _, storage, collector = _make_stack()

        initial = {"x": 1}
        collector.start_execution(
            execution_id="e2",
            graph_name="test",
            initial_state=initial,
        )

        collector.record_step(
            execution_id="e2",
            node_name="a",
            state_before={"x": 1},
            state_after={"x": 2, "y": "new"},
        )
        collector.record_step(
            execution_id="e2",
            node_name="b",
            state_before={"x": 2, "y": "new"},
            state_after={"x": 3, "y": "updated", "z": True},
        )

        # Verify individual states.
        state_0 = storage.get_state_at_step("e2", 0)
        state_1 = storage.get_state_at_step("e2", 1)
        assert state_0 is not None
        assert state_1 is not None
        assert state_0["x"] == 2
        assert state_1["x"] == 3

        storage.close()
