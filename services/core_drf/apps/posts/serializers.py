from rest_framework import serializers
from .models import Post, Like, Comment
from apps.users.serializers import UserProfileSerializer

class PostSerializer(serializers.ModelSerializer):
    user = UserProfileSerializer(read_only=True)
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = (
            'id', 'user', 'caption', 'media_url',
            'likes_count', 'comments_count', 'ranking_score',
            'is_liked', 'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'user', 'likes_count', 'comments_count', 'ranking_score', 'created_at', 'updated_at')

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # Efficiently checks like status if prefetched
            return Like.objects.filter(post=obj, user=request.user).exists()
        return False


class PostCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = ('caption', 'media_url')


class CommentSerializer(serializers.ModelSerializer):
    user = UserProfileSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ('id', 'post', 'user', 'content', 'created_at')
        read_only_fields = ('id', 'user', 'created_at')
