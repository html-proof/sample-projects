"""
Spotify-level Recommendation Engine

Signals used:
  1. Listening history   → recently played songs & artists
  2. Liked songs         → positive signal
  3. Skipped songs       → negative signal (filtered out)
  4. Repeated listens    → strong positive
  5. Session activity    → current context
  6. Trending scores     → popularity boost
  7. Time of day         → contextual (morning/night)
  8. Saavn suggestions   → content-based seed
"""

from datetime import datetime
import time
from collections import Counter
from typing import Optional

from firebase.db_ops import (
    get_user_recently_played, get_liked_songs, get_user_profile, 
    get, get_followed_artists, get_user_languages,
    store_recommendations, get_stored_recommendations, ref, song_get
)
from services.saavn import (
    get_song_suggestions, search_songs, search_artists, search_albums,
    slim_song, slim_artist, slim_album, get_top_artists_by_language, get_song
)
from cache.store import get_cached, set_cached


# ─── Trending Score ───────────────────────────────────────────────────────────

def compute_trending_score(song_id: str) -> float:
    # Use global analytics for trending score
    stats = get(f"analytics/plays/{song_id}") or {}
    return stats.get("count", 0) * 2


def get_trending_songs(limit: int = 20) -> list:
    cached = get_cached("trending", "global", ttl=1800) # 30 mins
    if cached:
        return cached[:limit]

    data = get("analytics/plays") or {}
    scored = []
    for song_id, stats in data.items():
        if isinstance(stats, dict):
            count = stats.get("count", 0)
            data_to_spread = stats
        else:
            count = stats if isinstance(stats, int) else 0
            data_to_spread = {"count": count}
            
        score = count * 2
        scored.append({"songId": song_id, "score": score, **data_to_spread})

    scored.sort(key=lambda x: x["score"], reverse=True)
    result = scored[:50]
    set_cached("trending", "global", result)
    
    # Fallback to Saavn if analytics are empty
    if not result:
        from services.saavn import search_songs, slim_song
        try:
            raw = search_songs("trending songs", limit=limit)
            songs = raw.get("data", {}).get("results", [])
            # Map search results to the expected trending format
            result = [{"songId": s["id"], "score": 100, **s} for s in songs]
        except: pass
        
    return result[:limit]


# ─── Content-Based Filtering ──────────────────────────────────────────────────

def get_content_based(seed_song_id: str, skipped: set = None, limit: int = 10, quality: str = "medium") -> list:
    skipped = skipped or set()
    cache_key = f"suggestions_{seed_song_id}_{quality}"
    cached = get_cached("songs_cache", cache_key, ttl=86400) # 24 hours
    if cached:
        results = [s for s in cached if s["id"] not in skipped]
        return results[:limit]

    try:
        raw = get_song_suggestions(seed_song_id, limit=20)
        songs = raw.get("data", []) if isinstance(raw, dict) else []
        slim = [slim_song(s, quality=quality) for s in songs]
        set_cached("songs_cache", cache_key, slim)
        return [s for s in slim if s["id"] not in skipped][:limit]
    except Exception:
        return []


# ─── Behavior-Based Filtering ─────────────────────────────────────────────────

def get_engagement_score(song_id: str) -> float:
    # Simplified engagement score as we moved away from explicit skips tracking for now
    stats = get(f"analytics/plays/{song_id}") or {}
    plays = stats.get("count", 0)
    return plays * 1.0


# ─── Extract Favorite Artists ─────────────────────────────────────────────────

def detect_favorite_artists(song_ids: list) -> list:
    artist_counts = Counter()
    for sid in song_ids:
        # Get from cache
        song = song_get(sid)
        if song:
            # Handle both raw and slimmed data for favorite artist detection
            artist_data = song.get("artists", {})
            if isinstance(artist_data, dict) and "primary" in artist_data:
                primary = artist_data.get("primary", [])
                if primary:
                    artist_counts[primary[0].get("name", "")] += 1
            elif isinstance(song.get("artist"), str):
                artist_counts[song.get("artist")] += 1
    return [a for a, _ in artist_counts.most_common(5)]


# ─── Time-of-Day Context ──────────────────────────────────────────────────────

def get_time_context() -> str:
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    else:
        return "night"


def generate_artist_recommendations(user_id: str, languages: list, followed: dict, limit: int = 10, quality: str = "medium") -> list:
    """Generates personalized artist suggestions."""
    # 1. Start with top artists in preferred languages
    artists = get_top_artists_by_language(languages, limit=limit, quality=quality)
    
    # 2. Filter out already followed artists if possible
    if followed:
        followed_ids = set(followed.keys())
        artists = [a for a in artists if a["id"] not in followed_ids]
    
    return artists[:limit]


def generate_album_recommendations(user_id: str, languages: list, fav_artists: list, limit: int = 10, quality: str = "medium") -> list:
    """Generates personalized album suggestions."""
    all_albums = []
    seen_ids = set()
    
    # Search albums by favorite artists
    for artist_name in fav_artists[:3]:
        try:
            raw = search_albums(artist_name, limit=5)
            results = raw.get("data", {}).get("results", [])
            for alb in results:
                slim = slim_album(alb, quality=quality)
                if slim["id"] not in seen_ids:
                    # Filter by language if preferred
                    if not languages or slim["language"].lower() in [l.lower() for l in languages]:
                        all_albums.append(slim)
                        seen_ids.add(slim["id"])
        except Exception:
            continue
            
    return all_albums[:limit]


# ─── Main Recommendation Pipeline ─────────────────────────────────────────────

def get_recommendations(user_id: str, limit: int = 20, force_refresh: bool = False, quality: str = "medium") -> dict:
    """Entry point: Serves stored recommendations or triggers generation."""
    if not force_refresh:
        stored = get_stored_recommendations(user_id)
        if stored:
            # Check if stale (older than 30 mins)
            if (time.time() - stored.get("updatedAt", 0)) < 1800:
                # If quality matches or we don't care about cached quality
                # For simplicity, we just return stored, but we might want to re-slim if quality differs
                return stored

    # Generate fresh recommendations
    recs = generate_fresh_recommendations(user_id, limit=limit, quality=quality)
    
    # Store them
    store_recommendations(user_id, recs)
    return recs


def generate_fresh_recommendations(user_id: str, limit: int = 20, quality: str = "medium") -> dict:
    """The heavy lifting: generates and ranks recommendations."""
    history      = get_user_recently_played(user_id, limit=50)
    skipped      = set() 
    liked        = get_liked_songs(user_id)
    profile      = get_user_profile(user_id)
    followed     = get_followed_artists(user_id)
    pref_langs   = get_user_languages(user_id)
    time_context = get_time_context()

    recent_song_ids = history[:20]
    fav_artists     = detect_favorite_artists(history)

    personalized = []

    # 1. Content-based from recent songs
    seeds = recent_song_ids[:5]
    for seed in seeds:
        suggestions = get_content_based(seed, skipped, limit=10, quality=quality)
        personalized.extend(suggestions)

    # 2. Artist-based from followed artists
    if followed:
        for artist_id, meta in list(followed.items())[:3]:
            try:
                artist_name = meta.get("name")
                if artist_name:
                    raw = search_songs(artist_name, limit=5)
                    songs = raw.get("data", {}).get("results", [])
                    personalized.extend([slim_song(s, quality=quality) for s in songs])
            except Exception:
                continue

    # 3. Filter and Boost
    followed_ids = set(followed.keys())
    seen = set(recent_song_ids[-10:]) | skipped
    unique_recs = []
    
    for song in personalized:
        sid = song.get("id")
        if not sid or sid in seen:
            continue
            
        seen.add(sid)
        
        # Signal: Language Match
        song_lang = song.get("language", "").lower()
        if pref_langs and song_lang not in pref_langs:
            continue
            
        boost = 1.0
        
        # Signal: Followed Artist
        artist_id = song.get("artistId", "") 
        if artist_id in followed_ids:
            boost *= 3.0
            
        # Signal: Favorite Artist (from history)
        artist_name = song.get("artist", "")
        if any(a in artist_name for a in fav_artists):
            boost *= 1.5
            
        # Signal: Liked Song
        if sid in liked:
            boost *= 1.5

        eng = get_engagement_score(sid)
        song["_score"] = eng * boost
        unique_recs.append(song)

    unique_recs.sort(key=lambda x: x.get("_score", 0), reverse=True)

    personalized_clean = [{k: v for k, v in s.items() if not k.startswith("_")}
                          for s in unique_recs[:limit]]

    # 4. Generate Artist & Album recommendations
    artists_recs = generate_artist_recommendations(user_id, pref_langs, followed, limit=10, quality=quality)
    albums_recs  = generate_album_recommendations(user_id, pref_langs, fav_artists, limit=10, quality=quality)

    # 5. Trending fallback
    trending_raw = get_trending_songs(limit=20)
    
    # If using analytics data, we might need to slim/transform
    # If using search fallback, they are already somewhat slimmed/enriched
    trending_final = []
    seen_trending = set()
    
    for t in trending_raw:
        tid = t.get("songId") or t.get("id")
        if tid in seen_trending: continue
        
        # Determine if it's already slimmed (from search fallback) or raw (from analytics)
        if "streamUrl" in t:
            song = t
        else:
            # Need to fetch details if it's just ID+Score
            try:
                raw_s = get_song(tid)
                song = slim_song(raw_s["data"][0], quality=quality)
            except: continue
            
        if pref_langs and song.get("language", "").lower() not in pref_langs:
            continue
            
        trending_final.append(song)
        seen_trending.add(tid)
        if len(trending_final) >= 10: break

    return {
        "personalized":  personalized_clean,
        "artists":       artists_recs,
        "albums":        albums_recs,
        "trending":      trending_final,
        "context":       time_context,
        "favoriteArtists": fav_artists,
        "updatedAt": int(time.time()),
        "quality": quality
    }


# ─── Smart Shuffle Queue ──────────────────────────────────────────────────────

def build_smart_queue(user_id: str, seed_song_id: str, queue_size: int = 15, quality: str = "medium") -> list:
    skipped   = set() # get_skipped_songs(user_id) - disabled for now
    history   = get_user_recently_played(user_id, limit=20)
    recent    = {sid for sid in history[:10]}
    avoid     = skipped | recent

    suggestions = get_content_based(seed_song_id, avoid, limit=queue_size, quality=quality)

    # Artist deduplication - avoid same artist back-to-back
    queue = []
    last_artist = None
    deferred = []

    for song in suggestions:
        artist = song.get("artist", "")
        if artist == last_artist:
            deferred.append(song)
        else:
            queue.append(song)
            last_artist = artist

    queue.extend(deferred)
    return queue[:queue_size]


# ─── Daily Mix Generator ──────────────────────────────────────────────────────

def generate_daily_mix(user_id: str) -> list:
    history     = get_user_recently_played(user_id, limit=100)
    skipped     = set() # get_skipped_songs(user_id) - disabled
    fav_artists = detect_favorite_artists(history) # history is just IDs now, need to fix
    recent_ids  = history[:5]

    mix = []
    seen = skipped.copy()

    for song_id in recent_ids:
        suggestions = get_content_based(song_id, seen, limit=4, quality="medium") # Defaulting for daily mix for now
        for s in suggestions:
            seen.add(s["id"])
            mix.append(s)

    # Search for favorite artists if mix is thin
    if len(mix) < 10 and fav_artists:
        for artist in fav_artists[:2]:
            try:
                raw = search_songs(artist, limit=5)
                songs = raw.get("data", {}).get("results", [])
                for s in songs:
                    slim = slim_song(s, quality="medium") # Defaulting for daily mix for now
                    if slim["id"] not in seen:
                        seen.add(slim["id"])
                        mix.append(slim)
            except Exception:
                pass

    return mix[:30]
