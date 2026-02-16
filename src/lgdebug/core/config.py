"""Configuration for the lgdebug system."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# Keys that change every run and clutter diffs — excluded by default.
DEFAULT_IGNORE_KEYS: frozenset[str] = frozenset(
    {
        "timestamp",
        "token_usage",
        "run_id",
        "request_id",
        "trace_id",
    }
)


@dataclass(frozen=True)
class DebugConfig:
    """Immutable configuration for a debugging session.

    Attributes:
        enabled: Master switch. When False, all instrumentation is a no-op.
        db_path: Path to the SQLite database file.
        checkpoint_interval: Full state snapshot every N steps (rest are diffs).
        ignore_keys: State keys excluded from diff computation.
        max_state_size_bytes: Safety limit per serialized state snapshot.
        server_host: Host for the debug API server.
        server_port: Port for the debug API server.
        auto_open_browser: Open the visualizer on `lgdebug run`.
    """

    enabled: bool = True
    db_path: Path = field(default_factory=lambda: Path(".lgdebug") / "debug.db")
    checkpoint_interval: int = 10
    ignore_keys: frozenset[str] = DEFAULT_IGNORE_KEYS
    max_state_size_bytes: int = 10 * 1024 * 1024  # 10 MB
    server_host: str = "127.0.0.1"
    server_port: int = 6274
    auto_open_browser: bool = True

    @property
    def server_url(self) -> str:
        return f"http://{self.server_host}:{self.server_port}"
