import os
import json
import asyncio
import logging
from typing import Dict, List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Realtime WebSockets"])

class NotificationPayload(BaseModel):
    target_user_id: str
    event: str
    message: str
    data: Optional[dict] = None

class NotificationConnectionManager:
    """
    Manages active WebSocket connections mapped by user_id.
    Subscribes to Redis Pub/Sub channels (user:notifications:<user_id>)
    to distribute real-time notifications across distributed worker nodes.
    """
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.listener_tasks: Dict[str, asyncio.Task] = {}
        self._in_memory_queues: Dict[str, List[asyncio.Queue]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
            self._in_memory_queues[user_id] = []
            # Start background Redis/local pubsub listener for this user
            self.listener_tasks[user_id] = asyncio.create_task(self._listen_for_notifications(user_id))
        
        self.active_connections[user_id].append(websocket)
        queue = asyncio.Queue()
        self._in_memory_queues[user_id].append(queue)
        logger.info("WebSocket connected for user: %s (Total: %d)", user_id, len(self.active_connections[user_id]))

    def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                idx = self.active_connections[user_id].index(websocket)
                self.active_connections[user_id].remove(websocket)
                if user_id in self._in_memory_queues and idx < len(self._in_memory_queues[user_id]):
                    self._in_memory_queues[user_id].pop(idx)

            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                del self._in_memory_queues[user_id]
                if user_id in self.listener_tasks:
                    self.listener_tasks[user_id].cancel()
                    del self.listener_tasks[user_id]
                logger.info("All WebSocket connections closed for user: %s", user_id)

    async def send_direct_notification(self, user_id: str, payload: dict):
        """Dispatches an in-process notification to all active sockets for a user"""
        if user_id in self.active_connections:
            serialized = json.dumps(payload)
            for ws in list(self.active_connections[user_id]):
                try:
                    await ws.send_text(serialized)
                except Exception as e:
                    logger.warning("Error pushing to websocket for %s: %s", user_id, str(e))

    async def _listen_for_notifications(self, user_id: str):
        """
        Background worker that subscribes to Redis channel user:notifications:<user_id>
        and pushes incoming events to all connected clients.
        """
        redis_host = os.getenv("REDIS_HOST", "127.0.0.1")
        redis_port = int(os.getenv("REDIS_PORT", 6379))
        channel_name = f"user:notifications:{user_id}"

        # Try connecting to Redis async pubsub
        try:
            import redis.asyncio as aioredis
            r = aioredis.Redis(
                host=redis_host,
                port=redis_port,
                decode_responses=True,
                socket_connect_timeout=0.1,
                socket_timeout=0.1
            )
            pubsub = r.pubsub()
            await asyncio.wait_for(pubsub.subscribe(channel_name), timeout=0.2)
            logger.info("Subscribed to Redis PubSub channel: %s", channel_name)

            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                    except Exception:
                        data = {"raw": message["data"]}
                    await self.send_direct_notification(user_id, data)
                await asyncio.sleep(0.05)

        except asyncio.CancelledError:
            logger.info("PubSub listener cancelled for user: %s", user_id)
        except Exception as e:
            logger.info("Redis PubSub unavailable (%s). Falling back to direct in-memory dispatcher.", str(e))
            # Keep listener alive for in-memory dispatcher
            try:
                while True:
                    await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                pass


manager = NotificationConnectionManager()


@router.websocket("/ws/notifications/{user_id}")
async def websocket_notifications_endpoint(websocket: WebSocket, user_id: str):
    """
    Real-time Duplex WebSocket Endpoint for Notifications & Alerts.
    Subscribes client to user:notifications:<user_id> channel.
    """
    await manager.connect(user_id, websocket)
    try:
        # Handshake confirmation
        await websocket.send_text(json.dumps({
            "event": "connection_established",
            "user_id": user_id,
            "status": "listening_to_realtime_events"
        }))

        # Client keep-alive / ping loop
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"event": "pong"}))
            else:
                # Echo client custom messages
                await websocket.send_text(json.dumps({"event": "ack", "received": data}))

    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)


@router.post("/api/v1/notifications/dispatch", status_code=status.HTTP_200_OK)
async def dispatch_notification_manually(payload: NotificationPayload):
    """
    HTTP Webhook/Endpoint to broadcast an instant real-time notification to a user.
    """
    event_data = {
        "event": payload.event,
        "message": payload.message,
        "data": payload.data or {}
    }
    await manager.send_direct_notification(payload.target_user_id, event_data)
    
    # Also publish to Redis PubSub if available
    try:
        import redis.asyncio as aioredis
        r = aioredis.Redis(
            host=os.getenv("REDIS_HOST", "127.0.0.1"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            socket_connect_timeout=0.1,
            socket_timeout=0.1
        )
        await asyncio.wait_for(
            r.publish(f"user:notifications:{payload.target_user_id}", json.dumps(event_data)),
            timeout=0.2
        )
        await r.aclose()
    except Exception:
        pass

    return {
        "status": "dispatched",
        "target_user_id": payload.target_user_id,
        "active_clients": len(manager.active_connections.get(payload.target_user_id, []))
    }
