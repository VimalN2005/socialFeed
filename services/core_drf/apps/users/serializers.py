from rest_framework import serializers
from .models import User, Follow

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'bio', 'avatar_url')

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            bio=validated_data.get('bio', ''),
            avatar_url=validated_data.get('avatar_url', '')
        )
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'bio', 'avatar_url',
            'followers_count', 'following_count', 'is_celebrity', 'created_at'
        )
        read_only_fields = ('id', 'followers_count', 'following_count', 'is_celebrity', 'created_at')


class FollowSerializer(serializers.ModelSerializer):
    follower_username = serializers.ReadOnlyField(source='follower.username')
    followed_username = serializers.ReadOnlyField(source='followed.username')

    class Meta:
        model = Follow
        fields = ('id', 'follower', 'followed', 'follower_username', 'followed_username', 'created_at')
        read_only_fields = ('id', 'follower', 'created_at')
