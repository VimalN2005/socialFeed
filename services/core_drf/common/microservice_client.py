import os
import logging
from typing import List, Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

class FastAPIMicroserviceClient:
    r"""
    HTTP Client bridging Django REST Framework with the FastAPI Microservice.
    Used for:
    1. Offloading computationally intensive Min-Heap Feed Ranking ($O(N \log K)$).
    2. Requesting AI Content Intelligence, Hashtags & Moderation checks.
    Includes instant fallback to maintain 100% availability if microservice is restarting.
    """

    @classmethod
    def get_base_url(cls) -> str:
        host = os.getenv("FASTAPI_HOST", "127.0.0.1")
        port = os.getenv("FASTAPI_PORT", "8001")
        return f"http://{host}:{port}"

    @classmethod
    def rank_candidate_posts(cls, user_id: str, candidates: List[Dict[str, Any]], top_k: int = 20) -> List[Dict[str, Any]]:
        """
        Sends candidate posts to FastAPI for dynamic Min-Heap score decay ranking.
        """
        url = f"{cls.get_base_url()}/api/v1/feed/rank?top_k={top_k}"
        payload = {
            "user_id": str(user_id),
            "posts": candidates
        }

        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("results", [])
        except Exception as e:
            logger.warning("FastAPI ranking service call failed (%s). Using local fallback.", str(e))

        # Local fallback sorting by created_at
        return sorted(candidates, key=lambda x: x.get("created_at", ""), reverse=True)[:top_k]

    @classmethod
    def analyze_caption_ai(cls, caption: str) -> Dict[str, Any]:
        """
        Calls FastAPI AI service for hashtags, sentiment, and safety moderation.
        """
        url = f"{cls.get_base_url()}/api/v1/ai/suggest-tags"
        payload = {"caption": caption}

        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.post(url, json=payload)
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.warning("FastAPI AI service call failed (%s). Using local fallback.", str(e))

        # Local fallback
        import re
        tags = [f"#{tag}" for tag in re.findall(r'#(\w+)', caption)]
        return {
            "original_caption": caption,
            "suggested_hashtags": tags or ["#ScaleFeed"],
            "sentiment": "Neutral",
            "sentiment_score": 0.0,
            "is_safe": True,
            "moderation_flag": None,
            "estimated_engagement_score": 0.5,
            "generated_headline": caption[:60]
        }
