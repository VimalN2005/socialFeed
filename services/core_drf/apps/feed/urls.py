from django.urls import path
from .views import UserTimelineFeedView, HybridFeedAnalyticsView

urlpatterns = [
    path('timeline/', UserTimelineFeedView.as_view(), name='user_timeline_feed'),
    path('hybrid/', HybridFeedAnalyticsView.as_view(), name='hybrid_feed_analytics'),
]
