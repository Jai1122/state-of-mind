"""FastAPI debug server — serves execution data to the visualizer UI.

Endpoints:
    GET  /api/executions              — list all executions
    GET  /api/executions/{id}         — single execution details
    GET  /api/executions/{id}/steps   — all steps for an execution
    GET  /api/executions/{id}/state/{step_index} — reconstructed state at step
    GET  /api/executions/{id}/timeline — full timeline with states
    GET  /api/executions/{id}/routing — routing decisions
    GET  /api/executions/{id}/compare — compare two steps
    WS   /ws/live                     — live execution updates

The server also serves the built frontend as static files.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from lgdebug.core.collector import DebugCollector, EventCallback
from lgdebug.core.config import DebugConfig
from lgdebug.replay.engine import ReplayEngine
from lgdebug.storage.sqlite import SQLiteStorage

logger = logging.getLogger("lgdebug.server")

# WebSocket connection manager.
_ws_clients: set[WebSocket] = set()


def create_app(config: DebugConfig | None = None) -> FastAPI:
    """Create and configure the debug server FastAPI application."""
    if config is None:
        config = DebugConfig()

    app = FastAPI(
        title="lgdebug — LangGraph State Debugger",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
    )

    # CORS for local development (frontend on different port).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Shared state: storage and replay engine.
    storage = SQLiteStorage(config.db_path)
    replay = ReplayEngine(storage)

    @app.on_event("startup")
    async def startup() -> None:
        await storage.initialize()
        logger.info("Debug server started — db=%s", config.db_path)

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await storage.close()

    # --- API Routes ---

    @app.get("/api/executions")
    async def list_executions(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> list[dict[str, Any]]:
        return await storage.list_executions(limit=limit, offset=offset)

    @app.get("/api/executions/{execution_id}")
    async def get_execution(execution_id: str) -> dict[str, Any]:
        execution = await storage.get_execution(execution_id)
        if execution is None:
            raise HTTPException(status_code=404, detail="Execution not found")
        return execution.to_dict()

    @app.get("/api/executions/{execution_id}/steps")
    async def get_steps(execution_id: str) -> list[dict[str, Any]]:
        steps = await storage.list_steps(execution_id)
        if not steps:
            # Check if execution exists at all.
            execution = await storage.get_execution(execution_id)
            if execution is None:
                raise HTTPException(status_code=404, detail="Execution not found")
        return steps

    @app.get("/api/executions/{execution_id}/state/{step_index}")
    async def get_state_at_step(execution_id: str, step_index: int) -> dict[str, Any]:
        state = await replay.get_state_at_step(execution_id, step_index)
        if state is None:
            raise HTTPException(status_code=404, detail="State not found")
        return {"execution_id": execution_id, "step_index": step_index, "state": state}

    @app.get("/api/executions/{execution_id}/timeline")
    async def get_timeline(execution_id: str) -> list[dict[str, Any]]:
        timeline = await replay.get_full_timeline(execution_id)
        if not timeline:
            execution = await storage.get_execution(execution_id)
            if execution is None:
                raise HTTPException(status_code=404, detail="Execution not found")
        return timeline

    @app.get("/api/executions/{execution_id}/routing")
    async def get_routing(execution_id: str) -> list[dict[str, Any]]:
        return await storage.get_routing_decisions(execution_id)

    @app.get("/api/executions/{execution_id}/compare")
    async def compare_steps(
        execution_id: str,
        step_a: int = Query(..., ge=0),
        step_b: int = Query(..., ge=0),
    ) -> dict[str, Any]:
        result = await replay.compare_steps(execution_id, step_a, step_b)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    # --- WebSocket for live updates ---

    @app.websocket("/ws/live")
    async def websocket_live(ws: WebSocket) -> None:
        await ws.accept()
        _ws_clients.add(ws)
        logger.info("WebSocket client connected (total=%d)", len(_ws_clients))
        try:
            # Keep connection alive — client sends pings.
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            _ws_clients.discard(ws)
            logger.info("WebSocket client disconnected (total=%d)", len(_ws_clients))

    # --- Static file serving for the frontend ---

    frontend_dist = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
    else:
        @app.get("/")
        async def index() -> dict[str, str]:
            return {
                "message": "lgdebug API server running. Frontend not built.",
                "hint": "Run 'cd frontend && npm run build' to build the UI.",
                "docs": "/api/docs",
            }

    return app


async def broadcast_event(event_type: str, data: dict[str, Any]) -> None:
    """Send an event to all connected WebSocket clients."""
    if not _ws_clients:
        return

    message = json.dumps({"type": event_type, "data": data})
    disconnected: set[WebSocket] = set()

    for ws in _ws_clients:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.add(ws)

    _ws_clients.difference_update(disconnected)


def create_ws_subscriber() -> EventCallback:
    """Create an event callback that broadcasts to WebSocket clients."""

    async def subscriber(event_type: str, data: dict[str, Any]) -> None:
        await broadcast_event(event_type, data)

    return subscriber
