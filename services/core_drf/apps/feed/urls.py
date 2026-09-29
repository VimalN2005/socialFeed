from django.urls import path
from .views import UserTimelineFeedView

urlpatterns = [
    path('timeline/', UserTimelineFeedView.as_view(), name='user_timeline_feed'),
]
