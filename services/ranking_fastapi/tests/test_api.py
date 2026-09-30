import json
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_prometheus_metrics():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "scalefeed_feed_requests_total" in response.text
    assert "scalefeed_feed_latency_seconds" in response.text

def test_min_heap_feed_ranking():
    now = datetime.now(timezone.utc)
    candidates = [
        {
            "id": "post-old-viral",
            "caption": "Old post with many likes",
            "media_url": "https://cdn.example.com/p1.jpg",
            "likes_count": 1000,
            "comments_count": 200,
            "shares_count": 50,
            "created_at": (now - timedelta(days=3)).isoformat()
        },
        {
            "id": "post-fresh-trending",
            "caption": "Fresh trending post from today",
            "media_url": "https://cdn.example.com/p2.jpg",
            "likes_count": 80,
            "comments_count": 30,
            "shares_count": 15,
            "created_at": (now - timedelta(hours=1)).isoformat()
        },
        {
            "id": "post-new-cold",
            "caption": "Brand new post with 0 likes",
            "media_url": "",
            "likes_count": 0,
            "comments_count": 0,
            "shares_count": 0,
            "created_at": (now - timedelta(minutes=5)).isoformat()
        }
    ]

    payload = {
        "user_id": "test-user-123",
        "posts": candidates
    }

    response = client.post("/api/v1/feed/rank?top_k=2", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["returned_count"] == 2
    assert len(data["results"]) == 2
    assert "ranking_score" in data["results"][0]
    # Verify descending score order
    assert data["results"][0]["ranking_score"] >= data["results"][1]["ranking_score"]

def test_ai_suggest_tags_and_sentiment_positive():
    payload = {
        "caption": "Excited to launch our new high throughput system design project with django and redis! Amazing performance!"
    }
    response = client.post("/api/v1/ai/suggest-tags", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["sentiment"] == "Positive"
    assert data["sentiment_score"] > 0
    assert data["is_safe"] is True
    assert "#DjangoDev" in data["suggested_hashtags"]
    assert "#RedisCache" in data["suggested_hashtags"]
    assert data["estimated_engagement_score"] > 0.4

def test_ai_moderation_abusive_detection():
    payload = {
        "caption": "Click this link for crypto scam fraud money now"
    }
    response = client.post("/api/v1/ai/suggest-tags", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["is_safe"] is False
    assert data["moderation_flag"] is not None
    assert "scam" in data["moderation_flag"] or "fraud" in data["moderation_flag"]

def test_websocket_connection_and_heartbeat():
    with client.websocket_connect("/ws/notifications/test-user-ws") as websocket:
        initial = websocket.receive_json()
        assert initial["event"] == "connection_established"
        assert initial["user_id"] == "test-user-ws"

        # Test heartbeat ping-pong
        websocket.send_text("ping")
        pong = websocket.receive_json()
        assert pong["event"] == "pong"

def test_manual_notification_dispatch_endpoint():
    payload = {
        "target_user_id": "user-abc-999",
        "event": "new_follower",
        "message": "Alice started following you!",
        "data": {"follower_id": "alice-123"}
    }
    response = client.post("/api/v1/notifications/dispatch", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "dispatched"
    assert data["target_user_id"] == "user-abc-999"
