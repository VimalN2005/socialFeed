from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Optional
from algorithms.priority_feed import PriorityFeedRanker

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

@router.post("/rank")
def rank_user_feed(payload: RankFeedRequest, top_k: int = Query(20, ge=1, le=100)):
    """
    Ranks candidate posts using the Min-Heap priority decay algorithm in O(N log K) time.
    """
    posts_dicts = [post.model_dump() for post in payload.posts]
    ranked = PriorityFeedRanker.get_top_k_posts(posts_dicts, k=top_k)
    return {
        "user_id": payload.user_id,
        "total_evaluated": len(payload.posts),
        "returned_count": len(ranked),
        "results": ranked
    }
