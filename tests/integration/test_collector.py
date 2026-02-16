"""Integration test: collector → storage → replay pipeline."""

import tempfile
from pathlib import Path

import pytest

from lgdebug.core.collector import DebugCollector
from lgdebug.core.config import DebugConfig
from lgdebug.replay.engine import ReplayEngine
from lgdebug.storage.sqlite import SQLiteStorage


@pytest.fixture
async def setup():
    """Create a full stack: config → storage → collector → replay."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = DebugConfig(
            db_path=Path(tmpdir) / "test.db",
            checkpoint_interval=2,  # checkpoint every 2 steps for testing
        )
        storage = SQLiteStorage(config.db_path)
        await storage.initialize()
        collector = DebugCollector(config, storage)
        replay = ReplayEngine(storage)
        yield config, storage, collector, replay
        await storage.close()


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_record_and_replay(self, setup):
        _, storage, collector, replay = setup

        # Start execution.
        initial = {"query": "test", "count": 0}
        execution = await collector.start_execution(
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
            await collector.record_step(
                execution_id="e1",
                node_name=f"node_{i}",
                state_before=states[i],
                state_after=states[i + 1],
            )

        # End execution.
        await collector.end_execution(
            execution_id="e1",
            final_state=states[4],
        )

        # Verify execution was recorded.
        execution = await storage.get_execution("e1")
        assert execution is not None
        assert execution.step_count == 4

        # Verify timeline reconstruction.
        timeline = await replay.get_full_timeline("e1")
        assert len(timeline) == 4
        assert timeline[0]["node_name"] == "node_0"
        assert timeline[3]["node_name"] == "node_3"

        # Verify state at each step.
        for i, entry in enumerate(timeline):
            assert entry["state"]["count"] == i + 1

        # Verify state_at_step works for non-checkpoint steps.
        state_at_3 = await replay.get_state_at_step("e1", 3)
        assert state_at_3 is not None
        assert state_at_3["count"] == 4
        assert state_at_3["done"] is True

    @pytest.mark.asyncio
    async def test_compare_steps(self, setup):
        _, _, collector, replay = setup

        initial = {"x": 1}
        await collector.start_execution(
            execution_id="e2",
            graph_name="test",
            initial_state=initial,
        )

        await collector.record_step(
            execution_id="e2",
            node_name="a",
            state_before={"x": 1},
            state_after={"x": 2, "y": "new"},
        )
        await collector.record_step(
            execution_id="e2",
            node_name="b",
            state_before={"x": 2, "y": "new"},
            state_after={"x": 3, "y": "updated", "z": True},
        )

        comparison = await replay.compare_steps("e2", 0, 1)
        assert "diff" in comparison
        # x changed from 2 to 3.
        changed_paths = {e["path"] for e in comparison["diff"]["changed"]}
        assert "x" in changed_paths
