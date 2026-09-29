from fastapi import APIRouter, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

router = APIRouter(tags=["Observability & Metrics"])

# Prometheus Metrics Definitions
FEED_REQUEST_COUNT = Counter(
    "scalefeed_feed_requests_total",
    "Total number of feed requests evaluated",
    ["status"]
)

FEED_LATENCY_HISTOGRAM = Histogram(
    "scalefeed_feed_latency_seconds",
    "Time spent calculating and ranking feeds",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

CACHE_HIT_COUNTER = Counter(
    "scalefeed_cache_hits_total",
    "Cache hit count for timeline feed lookups"
)

CACHE_MISS_COUNTER = Counter(
    "scalefeed_cache_misses_total",
    "Cache miss count for timeline feed lookups"
)

@router.get("/metrics")
def get_prometheus_metrics():
    """
    Exposes real-time system metrics for Prometheus scraping & Grafana dashboards.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
