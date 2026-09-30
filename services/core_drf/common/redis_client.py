import os
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class InMemoryRedisMock:
    """
    In-memory fallback for local development & unit testing when Redis server is offline.
    Implements Sorted Sets (ZSET), Key-Value storage, and Pub/Sub simulation.
    """
    def __init__(self):
        self._zsets: Dict[str, Dict[str, float]] = {}
        self._kv: Dict[str, str] = {}
        self._pubsub_events: List[Dict[str, Any]] = []

    def zadd(self, key: str, mapping: Dict[str, float]):
        if key not in self._zsets:
            self._zsets[key] = {}
        for member, score in mapping.items():
            self._zsets[key][str(member)] = float(score)

    def zrevrange(self, key: str, start: int, stop: int) -> List[str]:
        if key not in self._zsets:
            return []
        sorted_items = sorted(self._zsets[key].items(), key=lambda x: x[1], reverse=True)
        if stop == -1:
            slice_items = sorted_items[start:]
        else:
            slice_items = sorted_items[start:stop + 1]
        return [item[0] for item in slice_items]

    def zcard(self, key: str) -> int:
        return len(self._zsets.get(key, {}))

    def zremrangebyrank(self, key: str, start: int, stop: int):
        if key not in self._zsets:
            return
        sorted_items = sorted(self._zsets[key].items(), key=lambda x: x[1])
        # In Redis, rank 0 is lowest score. If stop is negative like -501:
        total = len(sorted_items)
        actual_stop = total + stop if stop < 0 else stop
        if actual_stop >= 0:
            to_remove = sorted_items[start:actual_stop + 1]
            for item, _ in to_remove:
                del self._zsets[key][item]

    def set(self, key: str, value: str, ex: Optional[int] = None, nx: bool = False) -> bool:
        if nx and key in self._kv:
            return False
        self._kv[key] = str(value)
        return True

    def get(self, key: str) -> Optional[str]:
        return self._kv.get(key)

    def publish(self, channel: str, message: str) -> int:
        self._pubsub_events.append({"channel": channel, "message": message})
        return 1

    def delete(self, *keys):
        for k in keys:
            self._zsets.pop(k, None)
            self._kv.pop(k, None)


class ScaleFeedRedisClient:
    """
    Production-grade Redis Client Manager for ScaleFeed.
    Handles Feed Timelines (ZSET), Celebrity Posts, Task Idempotency, and Pub/Sub.
    """
    _instance = None
    _client = None
    _using_mock = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ScaleFeedRedisClient, cls).__new__(cls)
            cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        redis_host = os.getenv("REDIS_HOST", "127.0.0.1")
        redis_port = int(os.getenv("REDIS_PORT", 6379))
        redis_db = int(os.getenv("REDIS_DB", 0))

        # Instant raw socket probe (0.1s timeout) to prevent blocking on offline Redis
        import socket
        has_server = False
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.1)
            s.connect((redis_host, redis_port))
            s.close()
            has_server = True
        except Exception:
            has_server = False

        if has_server:
            try:
                import redis
                client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    socket_connect_timeout=0.5,
                    socket_timeout=0.5,
                    decode_responses=True
                )
                client.ping()
                self._client = client
                self._using_mock = False
                logger.info("Connected to Redis at %s:%s (DB %s)", redis_host, redis_port, redis_db)
                return
            except Exception as e:
                logger.warning("Redis ping failed (%s). Using InMemoryRedisMock.", str(e))

        logger.info("Using InMemoryRedisMock for local environment.")
        self._client = InMemoryRedisMock()
        self._using_mock = True

    @property
    def client(self):
        return self._client

    @property
    def is_mock(self) -> bool:
        return self._using_mock

    # ----------------- Feed Timeline (ZSET) Operations -----------------
    def add_to_user_feed(self, user_id: str, post_id: str, score: float):
        """
        ZADD feed:<user_id> score post_id
        Score is usually epoch timestamp or precalculated ranking score.
        """
        key = f"feed:{user_id}"
        self._client.zadd(key, {str(post_id): score})

    def get_user_feed_post_ids(self, user_id: str, start: int = 0, stop: int = 49) -> List[str]:
        """
        ZREVRANGE feed:<user_id> start stop
        Returns post IDs ordered by score descending.
        """
        key = f"feed:{user_id}"
        return self._client.zrevrange(key, start, stop)

    def trim_user_feed(self, user_id: str, max_size: int = 500):
        """
        ZREMRANGEBYRANK feed:<user_id> 0 -(max_size + 1)
        Binds timeline size to prevent unbounded memory growth.
        """
        key = f"feed:{user_id}"
        self._client.zremrangebyrank(key, 0, -(max_size + 1))

    # ----------------- Celebrity Post Pool -----------------
    def add_celebrity_post(self, celebrity_id: str, post_id: str, score: float):
        """
        Store celebrity post in dedicated celebrity stream: celebrity_posts:<celebrity_id>
        """
        key = f"celebrity_posts:{celebrity_id}"
        self._client.zadd(key, {str(post_id): score})
        # Keep latest 200 posts per celebrity in cache
        self._client.zremrangebyrank(key, 0, -201)

    def get_celebrity_post_ids(self, celebrity_id: str, count: int = 20) -> List[str]:
        """
        Fetch recent post IDs for a celebrity.
        """
        key = f"celebrity_posts:{celebrity_id}"
        return self._client.zrevrange(key, 0, count - 1)

    # ----------------- Pub/Sub & Notifications -----------------
    def publish_notification(self, target_user_id: str, event_data: dict):
        """
        PUBLISH user:notifications:<target_user_id> json_data
        Dispatches to WebSocket listeners across horizontal nodes.
        """
        channel = f"user:notifications:{target_user_id}"
        payload = json.dumps(event_data)
        self._client.publish(channel, payload)

    # ----------------- Idempotency & Locks -----------------
    def acquire_idempotency_lock(self, lock_key: str, ttl_seconds: int = 300) -> bool:
        """
        SET lock_key 1 EX ttl NX
        Guarantees that duplicate events (e.g. celery task retries) do not execute twice.
        """
        return bool(self._client.set(lock_key, "1", ex=ttl_seconds, nx=True))


# Singleton instance
redis_manager = ScaleFeedRedisClient()
