from rest_framework import generics, permissions
from apps.posts.serializers import PostSerializer
from apps.posts.pagination import CursorPaginationByCreatedAt
from .services import HybridFeedService

class UserTimelineFeedView(generics.ListAPIView):
    """
    Personalized Social Timeline Feed View.
    Enforces Keyset Cursor Pagination and Hybrid Fan-out Query Strategy.
    """
    serializer_class = PostSerializer
    pagination_class = CursorPaginationByCreatedAt
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return HybridFeedService.get_feed_queryset(self.request.user)
