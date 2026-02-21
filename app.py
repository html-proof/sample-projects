from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
import uvicorn

from routes import search, songs, artists, albums, playlists, events, recommendations, onboarding, home
from firebase.client import init_firebase
from services.trending import start_trending_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_firebase()
    start_trending_scheduler()
    yield
    # Shutdown (cleanup if needed)


app = FastAPI(
    title="Music Streaming API",
    description="Spotify-like recommendation backend powered by JioSaavn",
    version="1.0.0",
    lifespan=lifespan
)

# Middleware
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(search.router,          prefix="/api", tags=["Search"])
app.include_router(songs.router,           prefix="/api", tags=["Songs"])
app.include_router(artists.router,         prefix="/api", tags=["Artists"])
app.include_router(albums.router,          prefix="/api", tags=["Albums"])
app.include_router(playlists.router,       prefix="/api", tags=["Playlists"])
app.include_router(events.router,          prefix="/api", tags=["Events"])
app.include_router(recommendations.router, prefix="/api", tags=["Recommendations"])
app.include_router(onboarding.router,      prefix="/api", tags=["Onboarding"])
app.include_router(home.router,            prefix="/api", tags=["Home"])


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "music-streaming-api"}


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
