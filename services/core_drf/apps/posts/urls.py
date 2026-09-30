from django.urls import path
from .views import (
    PostListCreateView,
    PostDetailView,
    LikeToggleView,
    CommentListCreateView,
    PostAIAnalysisView
)

urlpatterns = [
    path('', PostListCreateView.as_view(), name='post_list_create'),
    path('ai-analyze/', PostAIAnalysisView.as_view(), name='post_ai_analyze'),
    path('<uuid:pk>/', PostDetailView.as_view(), name='post_detail'),
    path('<uuid:post_id>/like/', LikeToggleView.as_view(), name='post_like_toggle'),
    path('<uuid:post_id>/comments/', CommentListCreateView.as_view(), name='post_comments'),
]
