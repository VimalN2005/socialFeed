from django.urls import path
from .views import (
    RegisterView,
    UserProfileView,
    FollowUserView,
    UnfollowUserView,
    MutualConnectionsView
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='user_register'),
    path('me/', UserProfileView.as_view(), name='user_my_profile'),
    path('<str:username>/', UserProfileView.as_view(), name='user_profile_by_username'),
    path('<uuid:user_id>/follow/', FollowUserView.as_view(), name='user_follow'),
    path('<uuid:user_id>/unfollow/', UnfollowUserView.as_view(), name='user_unfollow'),
    path('<uuid:user_id>/mutual/', MutualConnectionsView.as_view(), name='user_mutual_connections'),
]
