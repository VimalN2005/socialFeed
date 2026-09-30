from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.posts.serializers import PostSerializer
from apps.posts.pagination import CursorPaginationByCreatedAt
from .services import HybridFeedService

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
