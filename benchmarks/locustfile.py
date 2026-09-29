import uuid
from locust import HttpUser, task, between

class SocialFeedLoadTestUser(HttpUser):
    """
    Simulates realistic user behavior:
    - 70% Feed reads (High Read Ratio)
    - 20% Post likes / engagement
    - 10% Post creations
    """
    wait_time = between(0.5, 2.0)

    def on_start(self):
        """Simulate user authentication and assign dummy token"""
        self.user_id = str(uuid.uuid4())
        self.headers = {
            "Authorization": f"Bearer mock-jwt-token-{self.user_id}",
            "Content-Type": "application/json"
        }

    @task(7)
    def fetch_timeline_feed(self):
        """High throughput cursor-based timeline fetch"""
        self.client.get("/api/v1/posts/feed/?limit=20", headers=self.headers, name="GET /api/v1/posts/feed/")

    @task(2)
    def like_post(self):
        """Simulates rapid like/engagement events"""
        dummy_post_id = str(uuid.uuid4())
        self.client.post(
            f"/api/v1/posts/{dummy_post_id}/like/",
            headers=self.headers,
            name="POST /api/v1/posts/:id/like/"
        )

    @task(1)
    def create_post(self):
        """Simulates post publishing triggering async fanout"""
        payload = {
            "caption": "Testing high-throughput post pipeline with Locust #ScaleFeed #SystemDesign",
            "media_url": "https://cdn.scalefeed.dev/media/sample.jpg"
        }
        self.client.post("/api/v1/posts/", json=payload, headers=self.headers, name="POST /api/v1/posts/")
