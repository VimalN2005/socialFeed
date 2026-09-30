import re
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Optional

router = APIRouter(prefix="/api/v1/ai", tags=["AI Intelligence"])

class CaptionAnalysisRequest(BaseModel):
    caption: str = Field(..., max_length=1500)

class ContentIntelligenceResponse(BaseModel):
    original_caption: str
    suggested_hashtags: List[str]
    sentiment: str
    sentiment_score: float  # -1.0 (very negative) to +1.0 (very positive)
    is_safe: bool
    moderation_flag: Optional[str] = None
    estimated_engagement_score: float  # 0.0 to 1.0
    generated_headline: str

# Dictionaries for NLP Rule-Based Classification
POSITIVE_WORDS = {
    "great", "awesome", "love", "amazing", "excited", "happy", "success",
    "winner", "cool", "scale", "innovative", "proud", "stellar", "breakthrough",
    "fast", "scalable", "efficient", "performance", "milestone"
}
NEGATIVE_WORDS = {
    "bad", "terrible", "horrible", "failed", "bug", "crash", "outage",
    "slow", "worst", "unacceptable", "broken", "disaster", "angry"
}
ABUSIVE_KEYWORDS = {"spam", "scam", "phishing", "hate", "abuse", "fraud", "illegal"}

TOPIC_TAG_MAP = {
    "django": "#DjangoDev",
    "fastapi": "#FastAPI",
    "python": "#PythonProgramming",
    "system": "#SystemDesign",
    "architecture": "#SoftwareArchitecture",
    "database": "#PostgreSQL",
    "postgres": "#PostgreSQL",
    "redis": "#RedisCache",
    "cache": "#CachingStrategies",
    "scale": "#Scalability",
    "scaling": "#HighThroughput",
    "docker": "#DevOps",
    "cloud": "#CloudComputing",
    "kubernetes": "#K8s",
    "event": "#EventDriven",
    "celery": "#DistributedSystems"
}

@router.post("/suggest-tags", response_model=ContentIntelligenceResponse)
def analyze_caption_and_suggest_tags(payload: CaptionAnalysisRequest):
    """
    AI Content Intelligence Microservice:
    1. Extracts and suggests trending hashtags based on semantic domain keywords.
    2. Sentiment analysis with score range [-1.0, 1.0].
    3. Automated safety & content moderation compliance check.
    4. Engagement estimation score based on topic density and structure.
    5. Automatic micro-headline extraction.
    """
    raw_text = payload.caption.strip()
    words = re.findall(r'\b[a-zA-Z]{3,}\b', raw_text.lower())
    
    # 1. Existing hashtags in text
    existing_hashtags = [f"#{tag}" for tag in re.findall(r'#(\w+)', raw_text)]

    # 2. Contextual Topic Suggestion
    suggested = set(existing_hashtags)
    for word in words:
        if word in TOPIC_TAG_MAP:
            suggested.add(TOPIC_TAG_MAP[word])

    if not suggested:
        suggested.update(["#ScaleFeed", "#Engineering", "#Tech"])

    # 3. Sentiment & Scoring
    pos_count = sum(1 for w in words if w in POSITIVE_WORDS)
    neg_count = sum(1 for w in words if w in NEGATIVE_WORDS)
    total_sentiment_words = pos_count + neg_count

    if total_sentiment_words > 0:
        sentiment_score = round((pos_count - neg_count) / total_sentiment_words, 2)
    else:
        sentiment_score = 0.0

    if sentiment_score > 0.2:
        sentiment = "Positive"
    elif sentiment_score < -0.2:
        sentiment = "Negative"
    else:
        sentiment = "Neutral"

    # 4. Moderation & Safety
    flagged_terms = [w for w in words if w in ABUSIVE_KEYWORDS]
    is_safe = len(flagged_terms) == 0
    moderation_flag = f"Flagged terms detected: {', '.join(flagged_terms)}" if not is_safe else None

    # 5. Engagement Score Estimation (0.0 to 1.0)
    # Higher for medium-length captions with hashtags and positive sentiment
    length_factor = min(len(words) / 30.0, 1.0) * 0.4
    tag_factor = min(len(suggested) / 5.0, 1.0) * 0.3
    sentiment_factor = (sentiment_score + 1.0) / 2.0 * 0.3
    estimated_engagement = round(length_factor + tag_factor + sentiment_factor, 2)

    # 6. Headline Generation
    sentences = re.split(r'[.!?\n]', raw_text)
    headline = sentences[0].strip() if sentences and sentences[0].strip() else raw_text[:60]
    if len(headline) > 60:
        headline = headline[:57] + "..."

    return ContentIntelligenceResponse(
        original_caption=raw_text,
        suggested_hashtags=sorted(list(suggested)),
        sentiment=sentiment,
        sentiment_score=sentiment_score,
        is_safe=is_safe,
        moderation_flag=moderation_flag,
        estimated_engagement_score=estimated_engagement,
        generated_headline=headline
    )
