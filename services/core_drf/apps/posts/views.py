from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Post, Like, Comment
from .serializers import PostSerializer, PostCreateSerializer, CommentSerializer
from .pagination import CursorPaginationByCreatedAt

class PostListCreateView(generics.ListCreateAPIView):
    """
    High-Performance Post List & Create API.
    - Uses CursorPaginationByCreatedAt for keyset seeking.
    - Uses select_related('user') to eliminate N+1 queries.
    """
    pagination_class = CursorPaginationByCreatedAt
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        return Post.objects.select_related('user').all()

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return PostCreateSerializer
        return PostSerializer

    def perform_create(self, serializer):
        post = serializer.save(user=self.request.user)
        # In Week 2, this will trigger the Celery fan-out pipeline
        return post


class PostDetailView(generics.RetrieveDestroyAPIView):
    """
    Retrieve or Delete a Post.
    """
    queryset = Post.objects.select_related('user').all()
    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def perform_destroy(self, instance):
        if instance.user != self.request.user:
            return Response(
                {"error": "You do not have permission to delete this post."},
                status=status.HTTP_403_FORBIDDEN
            )
        instance.delete()


class LikeToggleView(APIView):
    """
    Atomic Like / Unlike Toggle View.
    Uses database transactions and F() atomic increments to prevent concurrency races.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, post_id):
        post = get_object_or_404(Post, id=post_id)

        with transaction.atomic():
            like, created = Like.objects.get_or_create(user=request.user, post=post)
            if created:
                Post.objects.filter(id=post.id).update(likes_count=F('likes_count') + 1)
                message = "Liked post."
                liked = True
            else:
                like.delete()
                Post.objects.filter(id=post.id).update(likes_count=F('likes_count') - 1)
                message = "Unliked post."
                liked = False

        post.refresh_from_db(fields=['likes_count'])
        return Response({
            "message": message,
            "liked": liked,
            "likes_count": post.likes_count
        }, status=status.HTTP_200_OK)


class CommentListCreateView(generics.ListCreateAPIView):
    """
    Chronological Comment thread for a post.
    """
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        post_id = self.kwargs.get('post_id')
        return Comment.objects.select_related('user').filter(post_id=post_id)

    def perform_create(self, serializer):
        post = get_object_or_404(Post, id=self.kwargs.get('post_id'))
        serializer.save(user=self.request.user, post=post)
        Post.objects.filter(id=post.id).update(comments_count=F('comments_count') + 1)
