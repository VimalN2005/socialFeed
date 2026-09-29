import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    """
    Custom User Model with UUID Primary Key and Denormalized Social Graph Counters.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    bio = models.TextField(blank=True, default="")
    avatar_url = models.URLField(blank=True, default="")
    
    # Denormalized counters for O(1) profile queries
    followers_count = models.PositiveIntegerField(default=0)
    following_count = models.PositiveIntegerField(default=0)
    
    # Threshold flag for Hybrid Fan-out
    is_celebrity = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    REQUIRED_FIELDS = ['email']

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['username']),
            models.Index(fields=['email']),
            models.Index(fields=['is_celebrity']),
        ]

    def update_celebrity_status(self, threshold=25000):
        new_status = self.followers_count >= threshold
        if self.is_celebrity != new_status:
            self.is_celebrity = new_status
            self.save(update_fields=['is_celebrity'])


class Follow(models.Model):
    """
    Social Graph Junction Table representing Follower -> Followed relations.
    Optimized with Composite Unique Constraints and directional B-Tree Indexes.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    follower = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='following_relations'
    )
    followed = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='follower_relations'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['follower', 'followed'],
                name='unique_follower_followed'
            )
        ]
        indexes = [
            # High-speed seek for user's followers: WHERE followed_id = ? ORDER BY created_at DESC
            models.Index(fields=['followed', '-created_at']),
            # High-speed seek for who user is following: WHERE follower_id = ? ORDER BY created_at DESC
            models.Index(fields=['follower', '-created_at']),
        ]

    def __str__(self):
        return f"{self.follower.username} -> {self.followed.username}"
