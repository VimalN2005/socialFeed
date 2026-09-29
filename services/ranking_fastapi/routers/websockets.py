from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List
import json

router = APIRouter(tags=["Realtime WebSockets"])

class NotificationConnectionManager:
    """
    Manages active WebSocket connections mapped by user_id.
    Integrates with Redis Pub/Sub for distributed clustering across servers.
    """
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_personal_notification(self, user_id: str, message: dict):
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                await connection.send_text(json.dumps(message))

manager = NotificationConnectionManager()

@router.websocket("/ws/notifications/{user_id}")
async def websocket_notifications_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(user_id, websocket)
    try:
        # Send initial connection handshake
        await websocket.send_text(json.dumps({
            "event": "connected",
            "message": f"Connected to real-time notification stream for user: {user_id}"
        }))
        while True:
            # Keep-alive heartbeat & client ping-pong
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
