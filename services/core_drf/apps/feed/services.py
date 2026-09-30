import logging
from typing import List, Dict, Any, Tuple
from django.db.models import QuerySet

from common.redis_client import redis_manager
from apps.users.models import Follow, User
from apps.posts.models import Post

logger = logging.getLogger(__name__)

class HybridFeedService:
    """
    Production Hybrid Fan-out Timeline Aggregator.
    
    Architecture:
    1. Standard Accounts (Fan-out-on-Write):
       - Follower timelines are pre-computed and stored in Redis ZSET: feed:<user_id>
    2. Celebrity Accounts (Fan-out-on-Read):
       - Celebrity posts are pulled dynamically on-demand from: celebrity_posts:<celeb_id>
    3. Merging:
       - Merges standard post IDs and celebrity post IDs in-memory.
       - Hydrates full ORM Post objects in a single batch query (select_related).
       - Falls back gracefully to Database (Cache-Aside) if Redis is cold.
    """

    @classmethod
    def get_user_feed(cls, user, limit: int = 20, offset: int = 0) -> Tuple[List[Post], str, int]:
        """
        Returns:
            (posts_list, source_type, celebrity_merged_count)
            source_type: 'redis_hybrid' or 'db_fallback'
        """
        user_id_str = str(user.id)

        # 1. Fetch pre-computed standard posts from Redis ZSET
        cached_post_ids = redis_manager.get_user_feed_post_ids(
            user_id_str,
            start=offset,
            stop=offset + limit + 15  # buffer for merging
        )

        # 2. Check for followed celebrities (Fan-out-on-Read)
        followed_celebrities = Follow.objects.filter(
            follower=user,
            followed__is_celebrity=True
        ).values_list('followed_id', flat=True)

        celebrity_post_ids = []
        for celeb_id in followed_celebrities:
            celeb_ids = redis_manager.get_celebrity_post_ids(str(celeb_id), count=10)
            if not celeb_ids:
                # DB fallback for celebrity recent posts if cache cold
                celeb_ids = list(Post.objects.filter(user_id=celeb_id).order_by('-created_at').values_list('id', flat=True)[:10])
                for cid in celeb_ids:
                    redis_manager.add_celebrity_post(str(celeb_id), str(cid), 0.0)
            celebrity_post_ids.extend([str(cid) for cid in celeb_ids])

        # 3. If Redis has data, merge and hydrate
        if cached_post_ids or celebrity_post_ids:
            all_candidate_ids = list(dict.fromkeys(cached_post_ids + celebrity_post_ids))
            
            # Single batch query with select_related to eliminate N+1
            posts_by_id = {
                str(post.id): post
                for post in Post.objects.filter(id__in=all_candidate_ids).select_related('user')
            }

            # Sort by creation time descending
            hydrated_posts = [
                posts_by_id[pid] for pid in all_candidate_ids if pid in posts_by_id
            ]
            hydrated_posts.sort(key=lambda p: p.created_at, reverse=True)

            paged_posts = hydrated_posts[:limit]
            return paged_posts, "redis_hybrid", len(celebrity_post_ids)

        # 4. Cache-Aside Fallback: Query directly from DB
        logger.info("Cache miss for user %s. Executing DB fallback and warming cache.", user_id_str)
        following_ids = list(Follow.objects.filter(follower=user).values_list('followed_id', flat=True))
        following_ids.append(user.id)

        db_posts = list(
            Post.objects.filter(user_id__in=following_ids)
            .select_related('user')
            .order_by('-created_at')[offset:offset + limit]
        )

        # Warm up user's Redis feed cache asynchronously or inline
        for p in db_posts:
            redis_manager.add_to_user_feed(user_id_str, str(p.id), p.created_at.timestamp())

        return db_posts, "db_fallback", 0

    @classmethod
    def get_feed_queryset(cls, user) -> QuerySet:
        """Compatibility method for standard DRF ViewSets / CursorPagination"""
        following_ids = list(Follow.objects.filter(follower=user).values_list('followed_id', flat=True))
        following_ids.append(user.id)
        return Post.objects.filter(user_id__in=following_ids).select_related('user').order_by('-created_at')
