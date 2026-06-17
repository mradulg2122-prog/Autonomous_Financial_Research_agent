"""
ARA-1 WebSocket Manager
Real-time streaming of agent trace events to connected clients.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket
from backend.core.logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """Manages WebSocket connections per research session."""

    def __init__(self) -> None:
        # Map: session_id -> list of WebSocket connections
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        if session_id not in self._connections:
            self._connections[session_id] = []
        self._connections[session_id].append(websocket)
        logger.info("ws_connected", session_id=session_id)

    async def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        conns = self._connections.get(session_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self._connections.pop(session_id, None)
        logger.info("ws_disconnected", session_id=session_id)

    async def broadcast_to_session(
        self, session_id: str, event_type: str, data: Any
    ) -> None:
        """Send a message to all connections for a session."""
        message = json.dumps({
            "type": event_type,
            "session_id": session_id,
            "data": data,
        }, default=str)

        dead_sockets = []
        for ws in self._connections.get(session_id, []):
            try:
                await ws.send_text(message)
            except Exception:
                dead_sockets.append(ws)

        for ws in dead_sockets:
            await self.disconnect(ws, session_id)

    async def broadcast_agent_trace(
        self, session_id: str, agent: str, status: str, data: Any = None
    ) -> None:
        await self.broadcast_to_session(session_id, "agent_trace", {
            "agent": agent,
            "status": status,
            "data": data,
        })

    async def broadcast_tool_call(
        self, session_id: str, tool: str, args: dict, result: Any = None
    ) -> None:
        await self.broadcast_to_session(session_id, "tool_call", {
            "tool": tool,
            "args": args,
            "result": result,
        })

    async def broadcast_status(self, session_id: str, status: str, message: str = "") -> None:
        await self.broadcast_to_session(session_id, "status", {
            "status": status,
            "message": message,
        })

    def get_connection_count(self, session_id: str) -> int:
        return len(self._connections.get(session_id, []))


# Singleton manager
ws_manager = ConnectionManager()
