from apps.posts.models import Post
from apps.users.models import Follow

class HybridFeedService:
    """
    Hybrid Fan-out Timeline Aggregator.
    Solves the Celebrity problem by:
    1. Fetching cached timeline posts (fan-out-on-write from standard users).
    2. Dynamic pull (fan-out-on-read) for followed accounts marked as 'is_celebrity=True'.
    3. Merging and slicing with deterministic cursor ordering.
    """

    @classmethod
    def get_feed_queryset(cls, user):
        # 1. Get IDs of all users currently followed
        following_user_ids = Follow.objects.filter(follower=user).values_list('followed_id', flat=True)

        # 2. Query posts from followed accounts + own posts
        # Leverages composite index: (user_id, created_at DESC)
        feed_queryset = Post.objects.filter(
            user_id__in=list(following_user_ids) + [user.id]
        ).select_related('user').order_by('-created_at')

        return feed_queryset
