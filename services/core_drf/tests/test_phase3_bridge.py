from django.test import TestCase
from rest_framework.test import APIClient
from apps.users.models import User, Follow
from apps.posts.models import Post

class Phase3BridgeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="phase3_user",
            email="phase3@example.com",
            password="password123"
        )
        self.client.force_authenticate(user=self.user)

        # Create some test posts
        for i in range(5):
            Post.objects.create(
                user=self.user,
                caption=f"Post #{i} testing Min-Heap decayed ranking algorithm with redis and django #ScaleFeed",
                likes_count=i * 15,
                comments_count=i * 5
            )

    def test_smart_ranked_feed_endpoint(self):
        """GET /api/v1/feed/ranked/ must return algorithmic ranked results"""
        response = self.client.get('/api/v1/feed/ranked/?top_k=3')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["algorithm"], "decayed_gravity_min_heap")
        self.assertLessEqual(data["ranked_count"], 3)
        self.assertIn("results", data)
        self.assertTrue(len(data["results"]) > 0)

    def test_post_ai_analyze_endpoint(self):
        """POST /api/v1/posts/ai-analyze/ must return AI suggestions, sentiment, safety"""
        payload = {
            "caption": "Excited about deploying our new scalable redis cache architecture on kubernetes! #Performance"
        }
        response = self.client.post('/api/v1/posts/ai-analyze/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("suggested_hashtags", data)
        self.assertIn("sentiment", data)
        self.assertIn("is_safe", data)
        self.assertTrue(data["is_safe"])
        self.assertIn("estimated_engagement_score", data)
