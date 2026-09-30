import time
from fastapi import APIRouter, Query, status
from pydantic import BaseModel
from typing import List, Optional
from algorithms.priority_feed import PriorityFeedRanker
from routers.metrics import FEED_REQUEST_COUNT, FEED_LATENCY_HISTOGRAM

router = APIRouter(prefix="/api/v1/feed", tags=["Feed Ranking"])

class PostCandidate(BaseModel):
    id: str
    caption: str
    media_url: Optional[str] = ""
    likes_count: int = 0
    comments_count: int = 0
    shares_count: int = 0
    created_at: str

class RankFeedRequest(BaseModel):
    user_id: str
    posts: List[PostCandidate]

@router.post("/rank", status_code=status.HTTP_200_OK)
def rank_user_feed(payload: RankFeedRequest, top_k: int = Query(20, ge=1, le=100)):
    """
    Ranks candidate posts using the Min-Heap priority decay algorithm in O(N log K) time.
    Formula: Score = (Likes*2 + Comments*3 + Shares*5) / ((Age_Hours + 2)^1.5)
    Tracks latency and request metrics for Prometheus observability.
    """
    start_time = time.perf_counter()
    try:
        posts_dicts = [post.model_dump() for post in payload.posts]
        ranked = PriorityFeedRanker.get_top_k_posts(posts_dicts, k=top_k)
        
        FEED_REQUEST_COUNT.labels(status="success").inc()
        duration = time.perf_counter() - start_time
        FEED_LATENCY_HISTOGRAM.observe(duration)

        return {
            "user_id": payload.user_id,
            "algorithm": "decayed_gravity_min_heap",
            "gravity": PriorityFeedRanker.GRAVITY,
            "total_evaluated": len(payload.posts),
            "returned_count": len(ranked),
            "latency_ms": round(duration * 1000, 3),
            "results": ranked
        }
    except Exception as e:
        FEED_REQUEST_COUNT.labels(status="error").inc()
        raise e
