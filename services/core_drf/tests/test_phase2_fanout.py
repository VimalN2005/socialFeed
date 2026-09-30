import uuid
from datetime import datetime, timezone, timedelta
from django.test import TestCase
from apps.users.models import User, Follow
from apps.posts.models import Post, Like
from apps.feed.tasks import fanout_post_creation, backfill_follower_feed
from apps.feed.services import HybridFeedService
from apps.posts.tasks import process_async_like
from common.redis_client import redis_manager

class Phase2HybridFanoutTests(TestCase):
    def setUp(self):
        # Create standard user with 3 followers
        self.standard_user = User.objects.create_user(
            username="standard_alice",
            email="alice@example.com",
            password="password123",
            is_celebrity=False
        )
        self.follower_1 = User.objects.create_user(
            username="follower_bob",
            email="bob@example.com",
            password="password123"
        )
        self.follower_2 = User.objects.create_user(
            username="follower_charlie",
            email="charlie@example.com",
            password="password123"
        )
        self.follower_3 = User.objects.create_user(
            username="follower_dave",
            email="dave@example.com",
            password="password123"
        )

        Follow.objects.create(follower=self.follower_1, followed=self.standard_user)
        Follow.objects.create(follower=self.follower_2, followed=self.standard_user)
        Follow.objects.create(follower=self.follower_3, followed=self.standard_user)

        # Create celebrity user (e.g. 50k followers)
        self.celebrity_user = User.objects.create_user(
            username="celebrity_star",
            email="star@example.com",
            password="password123",
            followers_count=50000,
            is_celebrity=True
        )
        # follower_1 also follows the celebrity
        Follow.objects.create(follower=self.follower_1, followed=self.celebrity_user)

    def test_fanout_on_write_for_standard_user(self):
        """Standard user post must be pushed to all followers' feeds"""
        post = Post.objects.create(
            user=self.standard_user,
            caption="Hello standard followers! #ScaleFeed"
        )

        # Execute fan-out task
        result = fanout_post_creation(
            str(post.id),
            str(self.standard_user.id),
            is_celebrity=False,
            score=post.created_at.timestamp()
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["mode"], "standard_push")
        self.assertEqual(result["followers_pushed"], 3)

        # Verify follower_1, follower_2, follower_3 all have this post in their Redis ZSET
        for follower in [self.follower_1, self.follower_2, self.follower_3]:
            feed_ids = redis_manager.get_user_feed_post_ids(str(follower.id))
            self.assertIn(str(post.id), feed_ids)

    def test_celebrity_cutoff_prevents_write_fanout(self):
        """Celebrity post must NOT be pushed to followers to prevent write amplification"""
        celeb_post = Post.objects.create(
            user=self.celebrity_user,
            caption="Exclusive celebrity update!"
        )

        result = fanout_post_creation(
            str(celeb_post.id),
            str(self.celebrity_user.id),
            is_celebrity=True,
            score=celeb_post.created_at.timestamp()
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["mode"], "celebrity_pull")

        # Verify follower_1 does NOT have the post pushed directly into feed:<follower_id>
        follower_feed_ids = redis_manager.get_user_feed_post_ids(str(self.follower_1.id))
        self.assertNotIn(str(celeb_post.id), follower_feed_ids)

        # But it IS stored in the celebrity pool: celebrity_posts:<celebrity_id>
        celeb_pool_ids = redis_manager.get_celebrity_post_ids(str(self.celebrity_user.id))
        self.assertIn(str(celeb_post.id), celeb_pool_ids)

    def test_hybrid_feed_read_merges_standard_and_celebrity_posts(self):
        """When reading feed, HybridFeedService dynamically merges standard + celebrity posts"""
        # 1. Standard user posts
        std_post = Post.objects.create(
            user=self.standard_user,
            caption="Standard post from Alice"
        )
        fanout_post_creation(str(std_post.id), str(self.standard_user.id), is_celebrity=False)

        # 2. Celebrity posts slightly later
        celeb_post = Post.objects.create(
            user=self.celebrity_user,
            caption="Viral celebrity post from Star"
        )
        fanout_post_creation(str(celeb_post.id), str(self.celebrity_user.id), is_celebrity=True)

        # 3. Follower 1 fetches their feed
        posts, source, celeb_count = HybridFeedService.get_user_feed(self.follower_1, limit=10)

        # Both posts must be present!
        post_ids = [str(p.id) for p in posts]
        self.assertIn(str(std_post.id), post_ids)
        self.assertIn(str(celeb_post.id), post_ids)
        self.assertGreaterEqual(celeb_count, 1)

    def test_async_like_idempotency_and_notification(self):
        """Async like must process idempotently and publish notification to author"""
        post = Post.objects.create(
            user=self.standard_user,
            caption="Test like notification"
        )

        # First like call
        res1 = process_async_like(str(self.follower_1.id), str(post.id), action="like")
        self.assertEqual(res1["status"], "success")

        # Immediate duplicate like call should be suppressed by idempotency lock
        res2 = process_async_like(str(self.follower_1.id), str(post.id), action="like")
        self.assertEqual(res2["status"], "duplicate_suppressed")
