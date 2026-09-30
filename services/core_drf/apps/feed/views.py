from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.posts.serializers import PostSerializer
from apps.posts.pagination import CursorPaginationByCreatedAt
from .services import HybridFeedService
from common.microservice_client import FastAPIMicroserviceClient

class UserTimelineFeedView(generics.ListAPIView):
    """
    Keyset Cursor-Paginated Feed View (Mobile & Web Infinite Scroll).
    """
    serializer_class = PostSerializer
    pagination_class = CursorPaginationByCreatedAt
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return HybridFeedService.get_feed_queryset(self.request.user)


class HybridFeedAnalyticsView(APIView):
    """
    High-Performance Hybrid Fan-out Feed Endpoint with Observability Headers & Metadata.
    Shows whether feed was served from Redis cache or DB fallback, and how many celebrity posts were merged.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))

        posts, source, celeb_count = HybridFeedService.get_user_feed(
            request.user,
            limit=limit,
            offset=offset
        )

        serializer = PostSerializer(posts, many=True, context={'request': request})
        return Response({
            "source": source,
            "celebrity_posts_merged": celeb_count,
            "count": len(posts),
            "results": serializer.data
        }, status=status.HTTP_200_OK)


class SmartRankedFeedView(APIView):
    """
    Algorithmic Smart Feed Endpoint.
    Fetches raw candidates and passes them to FastAPI's Min-Heap Decayed Score
    engine to generate an engaging, non-chronological ranked feed.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        top_k = int(request.query_params.get('top_k', 20))
        
        # 1. Fetch raw candidate posts (up to 100 recent posts)
        candidate_qs = HybridFeedService.get_feed_queryset(request.user)[:100]
        
        candidate_payloads = [
            {
                "id": str(p.id),
                "caption": p.caption,
                "media_url": p.media_url,
                "likes_count": p.likes_count,
                "comments_count": p.comments_count,
                "shares_count": 0,
                "created_at": p.created_at.isoformat()
            }
            for p in candidate_qs
        ]
        
        # 2. Call FastAPI Min-Heap Ranker
        ranked_results = FastAPIMicroserviceClient.rank_candidate_posts(
            user_id=str(request.user.id),
            candidates=candidate_payloads,
            top_k=top_k
        )
        
        # 3. Hydrate full model objects in ranked order
        post_map = {str(p.id): p for p in candidate_qs}
        ranked_posts = [post_map[r["id"]] for r in ranked_results if r["id"] in post_map]
        
        serializer = PostSerializer(ranked_posts, many=True, context={'request': request})
        return Response({
            "algorithm": "decayed_gravity_min_heap",
            "total_candidates": len(candidate_payloads),
            "ranked_count": len(ranked_posts),
            "results": serializer.data
        }, status=status.HTTP_200_OK)
