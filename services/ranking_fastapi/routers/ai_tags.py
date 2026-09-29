import re
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List

router = APIRouter(prefix="/api/v1/ai", tags=["AI Intelligence"])

class CaptionAnalysisRequest(BaseModel):
    caption: str = Field(..., max_length=1000)

class CaptionAnalysisResponse(BaseModel):
    original_caption: str
    suggested_hashtags: List[str]
    sentiment: str
    is_safe: bool

# Lightweight keyword dictionary for instant inference
POSITIVE_KEYWORDS = {"great", "awesome", "love", "amazing", "excited", "happy", "success", "winner", "cool", "scale"}
FLAGGED_KEYWORDS = {"spam", "scam", "phishing", "hate", "abuse"}

@router.post("/suggest-tags", response_model=CaptionAnalysisResponse)
def analyze_caption_and_suggest_tags(payload: CaptionAnalysisRequest):
    """
    AI Content Intelligence:
    - Extracts or suggests trending hashtags based on caption contents.
    - Performs instant keyword sentiment classification.
    - Automated content moderation safety check.
    """
    text = payload.caption.lower()
    words = re.findall(r'\b\w+\b', text)
    
    # 1. Existing hashtags extraction
    existing_hashtags = [word for word in re.findall(r'#(\w+)', payload.caption)]

    # 2. Suggested hashtags based on recognized tech/social topics
    topic_map = {
        "django": "#DjangoDev",
        "fastapi": "#FastAPI",
        "python": "#PythonProgramming",
        "system": "#SystemDesign",
        "design": "#SystemArchitecture",
        "database": "#PostgreSQL",
        "redis": "#RedisCache",
        "scale": "#Scalability",
        "docker": "#DevOps",
    }
    suggested = set(existing_hashtags)
    for word in words:
        if word in topic_map:
            suggested.add(topic_map[word])

    if not suggested:
        suggested.update(["#ScaleFeed", "#Trending", "#Tech"])

    # 3. Sentiment & Safety analysis
    has_positive = any(w in POSITIVE_KEYWORDS for w in words)
    has_flagged = any(w in FLAGGED_KEYWORDS for w in words)

    sentiment = "Positive" if has_positive else "Neutral"
    is_safe = not has_flagged

    return CaptionAnalysisResponse(
        original_caption=payload.caption,
        suggested_hashtags=sorted(list(suggested)),
        sentiment=sentiment,
        is_safe=is_safe
    )
