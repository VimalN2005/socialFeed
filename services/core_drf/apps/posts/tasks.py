import logging
from datetime import datetime, timezone
from celery import shared_task
from django.db.models import F

from common.redis_client import redis_manager
from apps.posts.models import Post, Like
from apps.users.models import User

logger = logging.getLogger(__name__)

@shared_task(name="apps.posts.tasks.process_async_like")
def process_async_like(user_id: str, post_id: str, action: str = "like"):
    """
    Decoupled event task for Post Engagement (Like/Unlike):
    1. Enforces Idempotency to prevent duplicate task execution.
    2. Broadcasts real-time notification to the post author via Redis Pub/Sub.
    """
    lock_key = f"lock:like:{user_id}:{post_id}:{action}"
    if not redis_manager.acquire_idempotency_lock(lock_key, ttl_seconds=10):
        logger.warning("Duplicate like event suppressed by idempotency lock for user %s on post %s", user_id, post_id)
        return {"status": "duplicate_suppressed"}

    try:
        post = Post.objects.select_related('user').filter(id=post_id).first()
        if not post:
            return {"status": "error", "message": "post_not_found"}

        liker = User.objects.filter(id=user_id).first()
        liker_username = liker.username if liker else "Someone"

        # If user liked someone else's post, dispatch real-time WebSocket notification
        if action == "like" and str(post.user.id) != str(user_id):
            notification_payload = {
                "event": "post_liked",
                "post_id": str(post.id),
                "sender_id": str(user_id),
                "sender_username": liker_username,
                "message": f"{liker_username} liked your post!",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            redis_manager.publish_notification(str(post.user.id), notification_payload)
            logger.info("Published real-time like notification to author %s", post.user.id)

        return {"status": "success", "action": action, "post_id": post_id}

    except Exception as e:
        logger.error("Error in process_async_like: %s", str(e))
        return {"status": "error", "message": str(e)}
