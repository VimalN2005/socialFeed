from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, Follow
from .serializers import UserRegistrationSerializer, UserProfileSerializer, FollowSerializer

class RegisterView(generics.CreateAPIView):
    """
    Public registration endpoint. Generates initial JWT pair upon successful creation.
    """
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserProfileSerializer(user).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_201_CREATED)


class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    User Profile View (Read / Update own profile)
    """
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        username = self.kwargs.get('username')
        if username:
            return get_object_or_404(User, username=username)
        return self.request.user


class FollowUserView(APIView):
    """
    Atomic Follow Action.
    Uses DB Transactions & F() expressions to avoid race conditions.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, user_id):
        target_user = get_object_or_404(User, id=user_id)
        if target_user == request.user:
            return Response(
                {"error": "You cannot follow yourself."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            follow, created = Follow.objects.get_or_create(
                follower=request.user,
                followed=target_user
            )
            if not created:
                return Response(
                    {"message": "Already following this user."},
                    status=status.HTTP_200_OK
                )

            # Atomic Counter Increments
            User.objects.filter(id=request.user.id).update(following_count=F('following_count') + 1)
            User.objects.filter(id=target_user.id).update(followers_count=F('followers_count') + 1)
            target_user.refresh_from_db(fields=['followers_count'])
            target_user.update_celebrity_status()

        return Response(
            {"message": f"Successfully followed {target_user.username}."},
            status=status.HTTP_201_CREATED
        )


class UnfollowUserView(APIView):
    """
    Atomic Unfollow Action.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, user_id):
        target_user = get_object_or_404(User, id=user_id)

        with transaction.atomic():
            deleted, _ = Follow.objects.filter(
                follower=request.user,
                followed=target_user
            ).delete()

            if deleted:
                User.objects.filter(id=request.user.id).update(following_count=F('following_count') - 1)
                User.objects.filter(id=target_user.id).update(followers_count=F('followers_count') - 1)
                target_user.refresh_from_db(fields=['followers_count'])
                target_user.update_celebrity_status()
                return Response({"message": f"Unfollowed {target_user.username}."}, status=status.HTTP_200_OK)

        return Response({"error": "You are not following this user."}, status=status.HTTP_400_BAD_REQUEST)


class MutualConnectionsView(APIView):
    """
    Graph Algorithm: Mutual Friends / Connections.
    Finds intersection of users followed by both request.user and target_user.
    Complexity: O(min(|A|, |B|)) seek using database index set operations.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, user_id):
        target_user = get_object_or_404(User, id=user_id)
        
        my_following_ids = Follow.objects.filter(follower=request.user).values_list('followed_id', flat=True)
        target_following_ids = Follow.objects.filter(follower=target_user).values_list('followed_id', flat=True)

        mutual_user_ids = my_following_ids.intersection(target_following_ids)
        mutual_users = User.objects.filter(id__in=mutual_user_ids)[:50]

        return Response({
            "target_user": target_user.username,
            "mutual_count": mutual_users.count(),
            "mutual_users": UserProfileSerializer(mutual_users, many=True).data
        })
