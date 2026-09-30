import logging
from datetime import datetime, timezone
from celery import shared_task
from django.db import transaction

from common.redis_client import redis_manager
from apps.users.models import Follow, User
from apps.posts.models import Post

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1000

@shared_task(name="apps.feed.tasks.fanout_post_creation", bind=True, max_retries=3, default_retry_delay=5)
def fanout_post_creation(self, post_id: str, author_id: str, is_celebrity: bool, score: float = None):
    """
    Hybrid Fan-out Engine Task:
    1. If Celebrity (followers >= 25k): Push only to celebrity pool. Skip fanout-on-write.
    2. If Standard User: Push post_id into each follower's Redis ZSET in batches of 1,000.
    """
    if score is None:
        score = datetime.now(timezone.utc).timestamp()

    try:
        # Step 1: Celebrity Path (Fan-out-on-Read)
        if is_celebrity:
            logger.info("Author %s is marked as Celebrity. Pushing to celebrity post pool only.", author_id)
            redis_manager.add_celebrity_post(author_id, post_id, score)
            return {
                "status": "success",
                "mode": "celebrity_pull",
                "author_id": author_id,
                "post_id": post_id
            }

        # Step 2: Standard User Path (Fan-out-on-Write)
        logger.info("Author %s is standard user. Initiating fan-out-on-write.", author_id)
        
        # Also add to author's own timeline
        redis_manager.add_to_user_feed(author_id, post_id, score)

        # Batch query followers using directional index (followed_id, -created_at)
        follower_queryset = Follow.objects.filter(followed_id=author_id).values_list('follower_id', flat=True)
        
        total_pushed = 0
        follower_batch = []
        for follower_id in follower_queryset.iterator(chunk_size=CHUNK_SIZE):
            follower_batch.append(str(follower_id))
            if len(follower_batch) >= CHUNK_SIZE:
                _push_batch_to_followers(follower_batch, post_id, score)
                total_pushed += len(follower_batch)
                follower_batch = []

        if follower_batch:
            _push_batch_to_followers(follower_batch, post_id, score)
            total_pushed += len(follower_batch)

        logger.info("Fan-out-on-write completed for post %s to %d followers.", post_id, total_pushed)
        return {
            "status": "success",
            "mode": "standard_push",
            "author_id": author_id,
            "post_id": post_id,
            "followers_pushed": total_pushed
        }

    except Exception as exc:
        logger.error("Error during fanout_post_creation for post %s: %s", post_id, str(exc))
        raise self.retry(exc=exc)


def _push_batch_to_followers(follower_ids: list, post_id: str, score: float):
    """Helper to push a post to a batch of followers and trim feed size"""
    for fid in follower_ids:
        redis_manager.add_to_user_feed(fid, post_id, score)
        redis_manager.trim_user_feed(fid, max_size=500)


@shared_task(name="apps.feed.tasks.backfill_follower_feed")
def backfill_follower_feed(follower_id: str, followed_id: str):
    """
    Backfill Task: When User A follows User B, backfill User B's latest posts
    into User A's timeline cache.
    """
    try:
        followed_user = User.objects.filter(id=followed_id).first()
        if not followed_user or followed_user.is_celebrity:
            # Celebrity posts are resolved dynamically on read, so no backfill needed
            return {"status": "skipped", "reason": "user_is_celebrity_or_missing"}

        recent_posts = Post.objects.filter(user_id=followed_id).order_by('-created_at')[:30]
        count = 0
        for post in recent_posts:
            score = post.created_at.timestamp()
            redis_manager.add_to_user_feed(follower_id, str(post.id), score)
            count += 1

        redis_manager.trim_user_feed(follower_id, max_size=500)
        return {"status": "backfilled", "count": count}
    except Exception as e:
        logger.error("Backfill failed for follower %s: %s", follower_id, str(e))
        return {"status": "error", "message": str(e)}
