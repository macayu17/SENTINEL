"""WebSocket connection manager for real-time market data streaming."""

from typing import List
from fastapi import WebSocket
from ..utils.logger import get_logger

logger = get_logger("websocket")


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts market updates."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, data: dict) -> None:
        """Send data to all connected clients."""
        if not self.active_connections:
            return

        disconnected = []
        for connection in tuple(self.active_connections):
            try:
                await connection.send_json(data)
            except Exception:
                disconnected.append(connection)

        if disconnected:
            disconnected_ids = {id(connection) for connection in disconnected}
            before_count = len(self.active_connections)
            self.active_connections = [
                connection
                for connection in self.active_connections
                if id(connection) not in disconnected_ids
            ]
            removed_count = before_count - len(self.active_connections)
            logger.info(f"Removed {removed_count} disconnected clients. Total: {len(self.active_connections)}")

    @property
    def client_count(self) -> int:
        return len(self.active_connections)
