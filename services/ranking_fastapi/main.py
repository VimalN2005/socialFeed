from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import ranking, ai_tags, websockets, metrics

app = FastAPI(
    title="ScaleFeed Intelligence & Real-Time Engine",
    description="High-Throughput Ranking, AI Hashtag Intelligence, and WebSocket Gateway",
    version="1.0.0"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(ranking.router)
app.include_router(ai_tags.router)
app.include_router(websockets.router)
app.include_router(metrics.router)

@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "service": "ranking_fastapi",
        "version": "1.0.0"
    }
