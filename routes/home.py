from fastapi import APIRouter, Depends, Query
from middleware.auth import optional_user
from recommender.engine import get_recommendations
from firebase.db_ops import (
    get_user_recently_played, get_user_profile, get_trending, 
    get_liked_songs, get_user_languages, song_get
)
from services.saavn import get_top_artists_by_language, get_song, slim_song, search_songs

router = APIRouter()

@router.get("/home")
async def home_feed(user: dict = Depends(optional_user)):
    """Consolidated home feed based on user preferences and activity."""
    if not user:
        # Generic feed for guest users
        trending_raw = get_trending("global") or []
        # Firebase may return a dict instead of a list; normalize it
        if isinstance(trending_raw, dict):
            trending = list(trending_raw.values())[:10]
        else:
            trending = list(trending_raw)[:10]
        # Fetch trending song details
        songs = []
        for tid in trending:
            try:
                s = get_song(tid)
                if s.get("data"):
                    songs.append(slim_song(s["data"][0]))
            except: continue
        
        # Fallback: if no trending data, fetch popular songs from Saavn
        if not songs:
            try:
                fallback = search_songs("trending hits", page=1, limit=10)
                if isinstance(fallback, dict) and "data" in fallback:
                    data = fallback["data"]
                    results = data.get("results", []) if isinstance(data, dict) else []
                    songs = [slim_song(s) for s in results[:10]]
            except: pass
            
        return {
            "greeting": "Welcome to Music Streaming",
            "personalized": [],
            "trending": songs,
            "popularArtists": [],
            "recentlyPlayed": []
        }
    
    user_id = user["uid"]
    profile = get_user_profile(user_id)
    languages = get_user_languages(user_id)
    
    # 1. Personalized Recommendations (Serves stored or generates)
    recs = get_recommendations(user_id, limit=10)
    
    # 2. Recently Played
    recent_ids = get_user_recently_played(user_id, limit=10)
    recent_songs = []
    for sid in recent_ids:
        sdata = song_get(sid)
        if sdata:
            recent_songs.append(sdata)
        
    # 3. Popular Artists in selected languages
    popular_artists = []
    if languages:
        popular_artists = get_top_artists_by_language(languages, limit=5)
        
    # 4. Trending in selected languages
    # For now, we reuse the trending from recs which is already filtered by language
    trending = recs.get("trending", [])
    
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
