import uuid
from django.db import models
from django.conf import settings

class Post(models.Model):
    """
    Core Post Entity.
    Equipped with denormalized engagement counters and composite B-tree indexes
    tailored for deterministic keyset pagination.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='posts'
    )
    caption = models.TextField(blank=True, default="")
    media_url = models.URLField(max_length=500, blank=True, default="")
    
    # Denormalized counters for lightning-fast reads
    likes_count = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)
    
    # Algorithmic ranking score
    ranking_score = models.FloatField(default=0.0, db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            # High-speed timeline seek: WHERE user_id = ? ORDER BY created_at DESC
            models.Index(fields=['user', '-created_at']),
            # Global cursor seek index
            models.Index(fields=['-created_at', 'id']),
            models.Index(fields=['-ranking_score']),
        ]

    def __str__(self):
        return f"Post({self.id}) by {self.user.username}"


class Like(models.Model):
    """
    Post Likes junction table with unique constraint to prevent double-likes.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='likes'
    )
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='likes'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'post'], name='unique_user_post_like')
        ]
        indexes = [
            models.Index(fields=['post', '-created_at']),
        ]


class Comment(models.Model):
    """
    Post Comments table indexed chronologically for conversation threads.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    content = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['post', 'created_at']),
        ]
