from fastapi import APIRouter, Depends, Query, Header
from typing import Optional
from middleware.auth import optional_user
from recommender.engine import get_recommendations
from firebase.db_ops import (
    get_user_recently_played, get_user_profile, get_trending, 
    get_liked_songs, get_user_languages, song_get
)
from services.saavn import get_top_artists_by_language, get_song, slim_song, search_songs, get_trending_fallback

router = APIRouter()

@router.get("/home")
async def home_feed(user: Optional[dict] = Depends(optional_user), x_quality: str = Header("medium")):
    """Consolidated home feed based on user preferences and activity."""
    if not user:
        # Generic feed for guest users
        songs = get_trending_fallback(quality=x_quality, limit=10)
        artists = get_top_artists_by_language(limit=5)
        
        return {
            "greeting": "Welcome to Music Streaming",
            "personalized": {
                "songs": [],
                "artists": [],
                "albums": []
            },
            "trending": songs,
            "popularArtists": artists,
            "recentlyPlayed": []
        }
    
    user_id = user["uid"]
    profile = get_user_profile(user_id)
    languages = get_user_languages(user_id)
    
    # 1. Personalized Recommendations (Serves stored or generates)
    recs = get_recommendations(user_id, limit=10, quality=x_quality)
    
    # 2. Recently Played
    recent_ids = get_user_recently_played(user_id, limit=10)
    recent_songs = []
    for sid in recent_ids:
        sdata = song_get(sid)
        if sdata:
            recent_songs.append(sdata)
        
    # 3. Popular Artists - Use selected languages or defaults
    popular_artists = get_top_artists_by_language(languages, limit=5)
        
    # 4. Trending - Use personalized trending (which now has fallbacks built-in)
    trending = recs.get("trending", [])
    
    # Final fallback if trending is still somehow empty
    if not trending:
        trending = get_trending_fallback(quality=x_quality, limit=10)
        
    return {
        "greeting": f"Hello, {profile.get('name', 'User')}",
        "onboardingComplete": profile.get("onboardingComplete", False),
        "personalized": {
            "songs": recs.get("personalized", []),
            "artists": recs.get("artists", []),
            "albums": recs.get("albums", [])
        },
        "trending": trending,
        "popularArtists": popular_artists,
        "recentlyPlayed": recent_songs,
        "context": recs.get("context", "anytime")
    }
