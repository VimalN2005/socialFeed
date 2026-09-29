import heapq
from datetime import datetime, timezone
from typing import List, Dict, Any

class PriorityFeedRanker:
    """
    DSA Implementation: Feed Ranking using a Min-Heap (Priority Queue).
    
    Formula: Hacker News / Reddit Style Time-Decayed Engagement Score:
        Score = (Likes * 2 + Comments * 3 + Shares * 5) / ((Age_in_Hours + 2) ^ Gravity)
    
    Complexity:
        - Time: O(N log K) where N = total candidate posts, K = top-k requested items.
        - Space: O(K) memory for the min-heap buffer.
    """

    GRAVITY = 1.5

    @classmethod
    def calculate_post_score(cls, post: Dict[str, Any], current_time: datetime = None) -> float:
        if not current_time:
            current_time = datetime.now(timezone.utc)

        # Parse post creation timestamp
        created_at_raw = post.get("created_at")
        if isinstance(created_at_raw, str):
            created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
        elif isinstance(created_at_raw, datetime):
            created_at = created_at_raw
        else:
            created_at = current_time

        age_seconds = max((current_time - created_at).total_seconds(), 0)
        age_hours = age_seconds / 3600.0

        likes = post.get("likes_count", 0)
        comments = post.get("comments_count", 0)
        shares = post.get("shares_count", 0)

        # Base engagement calculation
        engagement = (likes * 2) + (comments * 3) + (shares * 5)
        # Add 1 base point to prevent newly published zero-like posts from having score 0
        numerator = engagement + 1.0
        denominator = (age_hours + 2.0) ** cls.GRAVITY

        return round(numerator / denominator, 6)

    @classmethod
    def get_top_k_posts(cls, candidate_posts: List[Dict[str, Any]], k: int = 20) -> List[Dict[str, Any]]:
        """
        Maintains a Min-Heap of size K.
        Each element in heap: (score, post_id, post_dict)
        """
        if not candidate_posts:
            return []

        min_heap = []
        current_time = datetime.now(timezone.utc)

        for post in candidate_posts:
            score = cls.calculate_post_score(post, current_time)
            post_with_score = {**post, "ranking_score": score}
            post_id = str(post.get("id", ""))

            # Min-heap item tuple: (score, post_id, post_data)
            item = (score, post_id, post_with_score)

            if len(min_heap) < k:
                heapq.heappush(min_heap, item)
            else:
                if score > min_heap[0][0]:
                    heapq.heapreplace(min_heap, item)

        # Extract sorted in descending order (highest score first)
        ranked_posts = [heapq.heappop(min_heap)[2] for _ in range(len(min_heap))]
        ranked_posts.reverse()
        return ranked_posts
