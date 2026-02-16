"""Synchronous SQLite storage backend for the instrumentation layer.

This avoids all async/event-loop issues when recording steps from within
LangGraph's execution engine, which may run sync node functions inside its
own event loop. Using stdlib sqlite3 means zero deadlock risk.

The async SQLiteStorage (sqlite.py) remains available for the debug server
which runs in its own dedicated event loop.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lgdebug.core.diff import apply_diff
from lgdebug.core.models import (
    Execution,
    ExecutionStep,
    RoutingDecision,
    StateDiff,
    StepStatus,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS executions (
    execution_id   TEXT PRIMARY KEY,
    graph_name     TEXT NOT NULL,
    started_at     TEXT NOT NULL,
    ended_at       TEXT,
    status         TEXT NOT NULL DEFAULT 'running',
    initial_state  TEXT NOT NULL DEFAULT '{}',
    final_state    TEXT,
    step_count     INTEGER NOT NULL DEFAULT 0,
    metadata       TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS steps (
    step_id        TEXT PRIMARY KEY,
    execution_id   TEXT NOT NULL,
    node_name      TEXT NOT NULL,
    step_index     INTEGER NOT NULL,
    timestamp_start TEXT NOT NULL,
    timestamp_end  TEXT,
    status         TEXT NOT NULL DEFAULT 'running',
    state_before   TEXT,
    state_after    TEXT,
    state_diff     TEXT NOT NULL DEFAULT '{"changed":[],"added":[],"removed":[]}',
    is_checkpoint  INTEGER NOT NULL DEFAULT 0,
    error          TEXT,
    metadata       TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (execution_id) REFERENCES executions(execution_id)
);

CREATE INDEX IF NOT EXISTS idx_steps_execution ON steps(execution_id, step_index);

CREATE TABLE IF NOT EXISTS routing_decisions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    step_id               TEXT NOT NULL,
    execution_id          TEXT NOT NULL,
    source_node           TEXT NOT NULL,
    target_node           TEXT NOT NULL,
    condition_description TEXT NOT NULL DEFAULT '',
    condition_inputs      TEXT NOT NULL DEFAULT '{}',
    evaluated_value       TEXT,
    FOREIGN KEY (step_id) REFERENCES steps(step_id),
    FOREIGN KEY (execution_id) REFERENCES executions(execution_id)
);

CREATE INDEX IF NOT EXISTS idx_routing_execution ON routing_decisions(execution_id);
"""


class SyncSQLiteStorage:
    """Thread-safe synchronous SQLite storage.

    Uses a threading lock so concurrent node executions don't corrupt writes.
    WAL mode allows concurrent reads (from the debug server) while we write.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Storage not initialized. Call initialize() first.")
        return self._conn

    # --- Executions ---

    def save_execution(self, execution: Execution) -> None:
        with self._lock:
            self.conn.execute(
                """INSERT OR REPLACE INTO executions
                   (execution_id, graph_name, started_at, ended_at, status,
                    initial_state, final_state, step_count, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    execution.execution_id,
                    execution.graph_name,
                    execution.started_at.isoformat(),
                    execution.ended_at.isoformat() if execution.ended_at else None,
                    execution.status.value,
                    json.dumps(execution.initial_state),
                    json.dumps(execution.final_state) if execution.final_state else None,
                    execution.step_count,
                    json.dumps(execution.metadata),
                ),
            )
            self.conn.commit()

    def update_execution(self, execution: Execution) -> None:
        with self._lock:
            self.conn.execute(
                """UPDATE executions SET
                   ended_at = ?, status = ?, final_state = ?, step_count = ?, metadata = ?
                   WHERE execution_id = ?""",
                (
                    execution.ended_at.isoformat() if execution.ended_at else None,
                    execution.status.value,
                    json.dumps(execution.final_state) if execution.final_state else None,
                    execution.step_count,
                    json.dumps(execution.metadata),
                    execution.execution_id,
                ),
            )
            self.conn.commit()

    def get_execution(self, execution_id: str) -> Execution | None:
        cursor = self.conn.execute(
            "SELECT * FROM executions WHERE execution_id = ?", (execution_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return _row_to_execution(row)

    def list_executions(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        cursor = self.conn.execute(
            "SELECT * FROM executions ORDER BY started_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [_row_to_execution(r).to_dict() for r in cursor.fetchall()]

    # --- Steps ---

    def save_step(self, step: ExecutionStep) -> None:
        with self._lock:
            self.conn.execute(
                """INSERT INTO steps
                   (step_id, execution_id, node_name, step_index, timestamp_start,
                    timestamp_end, status, state_before, state_after, state_diff,
                    is_checkpoint, error, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    step.step_id,
                    step.execution_id,
                    step.node_name,
                    step.step_index,
                    step.timestamp_start.isoformat(),
                    step.timestamp_end.isoformat() if step.timestamp_end else None,
                    step.status.value,
                    json.dumps(step.state_before) if step.state_before is not None else None,
                    json.dumps(step.state_after) if step.state_after is not None else None,
                    json.dumps(step.state_diff.to_dict()),
                    1 if step.is_checkpoint else 0,
                    step.error,
                    json.dumps(step.metadata),
                ),
            )
            self.conn.commit()

    def get_step(self, step_id: str) -> ExecutionStep | None:
        cursor = self.conn.execute(
            "SELECT * FROM steps WHERE step_id = ?", (step_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return _row_to_step(row)

    def list_steps(self, execution_id: str) -> list[dict[str, Any]]:
        cursor = self.conn.execute(
            "SELECT * FROM steps WHERE execution_id = ? ORDER BY step_index ASC",
            (execution_id,),
        )
        return [_row_to_step(r).to_dict() for r in cursor.fetchall()]

    def get_state_at_step(
        self, execution_id: str, step_index: int
    ) -> dict[str, Any] | None:
        cursor = self.conn.execute(
            """SELECT * FROM steps
               WHERE execution_id = ? AND step_index <= ? AND is_checkpoint = 1
               ORDER BY step_index DESC LIMIT 1""",
            (execution_id, step_index),
        )
        checkpoint_row = cursor.fetchone()

        if checkpoint_row is not None:
            checkpoint = _row_to_step(checkpoint_row)
            state = checkpoint.state_after or {}
            start_index = checkpoint.step_index + 1
        else:
            execution = self.get_execution(execution_id)
            if execution is None:
                return None
            state = execution.initial_state
            start_index = 0

        if start_index <= step_index:
            cursor = self.conn.execute(
                """SELECT * FROM steps
                   WHERE execution_id = ? AND step_index >= ? AND step_index <= ?
                   ORDER BY step_index ASC""",
                (execution_id, start_index, step_index),
            )
            for row in cursor.fetchall():
                step = _row_to_step(row)
                if step.is_checkpoint and step.state_after is not None:
                    state = step.state_after
                else:
                    state = apply_diff(state, step.state_diff)

        return state

    # --- Routing ---

    def save_routing_decision(self, decision: RoutingDecision) -> None:
        cursor = self.conn.execute(
            "SELECT execution_id FROM steps WHERE step_id = ?", (decision.step_id,)
        )
        row = cursor.fetchone()
        execution_id = row["execution_id"] if row else ""

        with self._lock:
            self.conn.execute(
                """INSERT INTO routing_decisions
                   (step_id, execution_id, source_node, target_node,
                    condition_description, condition_inputs, evaluated_value)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    decision.step_id,
                    execution_id,
                    decision.source_node,
                    decision.target_node,
                    decision.condition_description,
                    json.dumps(decision.condition_inputs),
                    json.dumps(decision.evaluated_value),
                ),
            )
            self.conn.commit()

    def get_routing_decisions(self, execution_id: str) -> list[dict[str, Any]]:
        cursor = self.conn.execute(
            "SELECT * FROM routing_decisions WHERE execution_id = ? ORDER BY id ASC",
            (execution_id,),
        )
        return [
            {
                "step_id": row["step_id"],
                "source_node": row["source_node"],
                "target_node": row["target_node"],
                "condition_description": row["condition_description"],
                "condition_inputs": json.loads(row["condition_inputs"]),
                "evaluated_value": json.loads(row["evaluated_value"]),
            }
            for row in cursor.fetchall()
        ]


# --- Row-to-model helpers ---


def _row_to_execution(row: sqlite3.Row) -> Execution:
    return Execution(
        execution_id=row["execution_id"],
        graph_name=row["graph_name"],
        started_at=datetime.fromisoformat(row["started_at"]).replace(tzinfo=timezone.utc),
        ended_at=(
            datetime.fromisoformat(row["ended_at"]).replace(tzinfo=timezone.utc)
            if row["ended_at"]
            else None
        ),
        status=StepStatus(row["status"]),
        initial_state=json.loads(row["initial_state"]),
        final_state=json.loads(row["final_state"]) if row["final_state"] else None,
        step_count=row["step_count"],
        metadata=json.loads(row["metadata"]),
    )


def _row_to_step(row: sqlite3.Row) -> ExecutionStep:
    diff_data = json.loads(row["state_diff"])
    return ExecutionStep(
        step_id=row["step_id"],
        execution_id=row["execution_id"],
        node_name=row["node_name"],
        step_index=row["step_index"],
        timestamp_start=datetime.fromisoformat(row["timestamp_start"]).replace(
            tzinfo=timezone.utc
        ),
        timestamp_end=(
            datetime.fromisoformat(row["timestamp_end"]).replace(tzinfo=timezone.utc)
            if row["timestamp_end"]
            else None
        ),
        status=StepStatus(row["status"]),
        state_before=json.loads(row["state_before"]) if row["state_before"] else None,
        state_after=json.loads(row["state_after"]) if row["state_after"] else None,
        state_diff=StateDiff(
            changed=diff_data.get("changed", []),
            added=diff_data.get("added", []),
            removed=diff_data.get("removed", []),
        ),
        is_checkpoint=bool(row["is_checkpoint"]),
        error=row["error"],
        metadata=json.loads(row["metadata"]),
    )
