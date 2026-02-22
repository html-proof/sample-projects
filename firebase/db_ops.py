from firebase_admin import db
from typing import Any, Optional
import time
import re


# ─── Generic Helpers ──────────────────────────────────────────────────────────

def ref(path: str):
    return db.reference(path)


# ─── Search Indexing (Spotify-Level Speed) ───────────────────────────────────

def generate_prefixes(text: str) -> list:
    """Break text into searchable prefixes (e.g. 'arijit' -> ['a', 'ar', 'ari'...])."""
    if not text:
        return []
    # Normalize: lowercase, remove special chars, split into words
    text = re.sub(r'[^a-zA-Z0-9\s]', '', text.lower())
    words = text.split()
    prefixes = set()
    for word in words:
        for i in range(1, len(word) + 1):
            prefixes.add(word[:i])
    # Also index the whole phrase prefixes
    phrase = "".join(words)
    for i in range(1, len(phrase) + 1):
        prefixes.add(phrase[:i])
    return list(prefixes)


def index_song_for_search(song_id: str, title: str, artist: str):
    """Adds a song ID to the prefix-based search index."""
    title_prefixes = generate_prefixes(title)
    artist_prefixes = generate_prefixes(artist)
    all_prefixes = set(title_prefixes + artist_prefixes)
    
    # We use a batch update or individual sets. For RTDB, we append song IDs to nodes.
    # To keep it efficient, we store as: prefix_index/{prefix}/{song_id} = True
    for p in all_prefixes:
        if len(p) < 2: continue # Skip single letters to avoid massive index nodes
        ref(f"prefix_index/{p}/{song_id}").set(True)


def search_local_index(query: str, limit: int = 10) -> list:
    """Instantly searches the local prefix_index in Firebase."""
    safe_prefix = re.sub(r'[^a-zA-Z0-9]', '', query.lower().strip())
    if not safe_prefix:
        return []
    
    # Get song IDs for this prefix
    data = get(f"prefix_index/{safe_prefix}")
    if not data or not isinstance(data, dict):
        return []
        
    song_ids = list(data.keys())[:limit]
    results = []
    for sid in song_ids:
        song_meta = song_get(sid)
        if song_meta:
            results.append(song_meta)
    return results


def get(path: str) -> Optional[Any]:
    return ref(path).get()


def set_val(path: str, value: Any):
    ref(path).set(value)


def update(path: str, value: dict):
    ref(path).update(value)


def push(path: str, value: Any):
    ref(path).push(value)


def delete(path: str):
    ref(path).delete()


# ─── Cache & Metadata Management ──────────────────────────────────────────────

def song_get(song_id: str) -> Optional[dict]:
    """Retrieves song metadata from the cache."""
    return get(f"songs/{song_id}")


def song_set(song_id: str, metadata: dict):
    """Caches song metadata."""
    metadata["updatedAt"] = int(time.time())
    set_val(f"songs/{song_id}", metadata)


def cache_get(query: str, ttl_seconds: int = 3600) -> Optional[list]:
    """Retrieves search results (hydrated) from the search index cache."""
    safe_key = query.lower().strip().replace("/", "_").replace(".", "_")[:100]
    data = get(f"search_index/{safe_key}")
    
    if data and (time.time() - data.get("timestamp", 0)) < ttl_seconds:
        song_ids = data.get("song_ids", [])
        if not song_ids:
            return []
            
        # Rehydrate results from deep song metadata cache
        results = []
        for sid in song_ids:
            song_meta = get(f"songs/{sid}")
            if song_meta:
                results.append(song_meta)
        
        # Only return if we actually recovered songs
        if results:
            return results
            
    return None

def normalize_query(q: str) -> str:
    """Helper to convert queries to a safe dictionary key format."""
    return q.lower().strip().replace("/", "_").replace(".", "_")[:100]

def cache_set(query: str, results: list):
    """Caches search results by indexing song IDs and storing metadata deeply."""
    safe_key = normalize_query(query)
    song_ids = []
    
    # Store the actual deep metadata
    for song in results[:20]:  # Limit to top 20
        sid = song.get("id")
        if sid:
            song_ids.append(sid)
            song_set(sid, song)  # Uses existing deep cache logic
            
    # Update search index
    set_val(f"search_index/{safe_key}", {
        "song_ids": song_ids,
        "timestamp": time.time()
    })
    
    # Index individual songs for instant prefix search
    for song in results:
        index_song_for_search(
            song.get("id"), 
            song.get("title") or song.get("name"), 
            song.get("artist")
        )


# ─── Generic Caching ──────────────────────────────────────────────────────────

def generic_cache_get(node: str, key: str, ttl_seconds: int) -> Optional[Any]:
    """Retrieves data from any cache node."""
    safe_key = key.replace("/", "_").replace(".", "_")[:100]
    data = get(f"{node}/{safe_key}")
    if data and (time.time() - data.get("timestamp", 0)) < ttl_seconds:
        return data.get("results")
    return None


def generic_cache_set(node: str, key: str, value: Any):
    """Stores data in any cache node."""
    safe_key = key.replace("/", "_").replace(".", "_")[:100]
    set_val(f"{node}/{safe_key}", {
        "results": value,
        "timestamp": time.time()
    })


# ─── User Activity ────────────────────────────────────────────────────────────

def record_play(user_id: str, song_id: str):
    """Records a song play for a user and updates global analytics."""
    # Update user history under user-centric node
    push(f"users/{user_id}/recently_played", {
        "songId": song_id,
        "playedAt": int(time.time())
    })
    
    # Update global analytics
    stats_ref = ref(f"analytics/plays/{song_id}")
    data = stats_ref.get() or {}
    count = data.get("count", 0)
    stats_ref.set({"count": count + 1})


def record_like(user_id: str, song_id: str):
    """Records a liked song for a user."""
    set_val(f"users/{user_id}/liked_songs/{song_id}", True)


def record_click(item_id: str):
    """Records a click event for global analytics."""
    stats_ref = ref(f"analytics/clicks/{item_id}")
    data = stats_ref.get() or {}
    count = data.get("count", 0)
    stats_ref.set({"count": count + 1})


def record_search(user_id: str, query: str):
    """Records user search history and global search analytics."""
    push(f"users/{user_id}/search_history", {
        "query": query,
        "timestamp": int(time.time())
    })
    
    # Update global analytics
    safe_query = query.lower().strip().replace("/", "_").replace(".", "_")[:100]
    stats_ref = ref(f"analytics/searches/{safe_query}")
    data = stats_ref.get() or {}
    count = data.get("count", 0)
    stats_ref.set({"count": count + 1})


# ─── Trending & Suggestions ───────────────────────────────────────────────────

def get_trending(category: str = "daily") -> list:
    """Retrieves trending song IDs."""
    return get(f"trending/{category}") or []


def set_trending(category: str, song_ids: list):
    """Sets trending song IDs."""
    set_val(f"trending/{category}", song_ids)


def get_suggestions(prefix: str) -> list:
    """Retrieves search suggestions for a prefix."""
    safe_prefix = prefix.lower().strip()[:20]
    return get(f"suggestions/{safe_prefix}") or []


def set_suggestions(prefix: str, suggestions: list):
    """Sets search suggestions for a prefix."""
    safe_prefix = prefix.lower().strip()[:20]
    set_val(f"suggestions/{safe_prefix}", suggestions)


# ─── Playlists ────────────────────────────────────────────────────────────────

def playlist_create(user_id: str, name: str) -> str:
    """Creates a new playlist and returns its unique ID."""
    playlist_data = {
        "name": name,
        "owner": user_id,
        "songs": {},
        "createdAt": int(time.time())
    }
    # Create the playlist and get auto-generated ID
    new_ref = ref("playlists").push(playlist_data)
    # Also add it to the user's playlist list if desired, 
    # but the recommendation shows playlists as a separate top-level node.
    return new_ref.key


def playlist_get(playlist_id: str) -> Optional[dict]:
    """Retrieves playlist details."""
    return get(f"playlists/{playlist_id}")


def playlist_add_song(playlist_id: str, song_id: str):
    """Adds a song to a playlist."""
    set_val(f"playlists/{playlist_id}/songs/{song_id}", True)


def playlist_get_songs(playlist_id: str) -> list:
    """Retrieves and rehydrates songs in a playlist."""
    playlist = playlist_get(playlist_id)
    if not playlist or "songs" not in playlist:
        return []
        
    song_ids = playlist["songs"].keys()
    results = []
    for sid in song_ids:
        song_meta = get(f"songs/{sid}")
        if song_meta:
            results.append(song_meta)
    return results

def get_user_playlists(user_id: str) -> list:
    """Retrieves all playlists owned by a user."""
    # This is an O(N) operation in Firebase RTDB without indexing. 
    # For a small app, we can fetch and filter.
    data = get("playlists") or {}
    user_playlists = []
    for pid, pdata in data.items():
        if pdata.get("owner") == user_id:
            user_playlists.append({"id": pid, **pdata})
    return user_playlists


# ─── Fetch User Data ──────────────────────────────────────────────────────────

def get_user_recently_played(user_id: str, limit: int = 20) -> list:
    """Retrieves the list of recently played song IDs for a user."""
    data = get(f"users/{user_id}/recently_played") or {}
    if isinstance(data, dict):
        # Items are dicts with playedAt
        items = sorted(data.values(), key=lambda x: x.get("playedAt", 0), reverse=True)
        return [item.get("songId") for item in items[:limit]]
    return []


def get_liked_songs(user_id: str) -> set:
    """Retrieves the set of liked song IDs for a user."""
    data = get(f"users/{user_id}/liked_songs") or {}
    return set(data.keys())


def get_user_profile(user_id: str) -> dict:
    """Retrieves user profile sub-node."""
    return get(f"users/{user_id}/profile") or {}


def get_or_create_user_profile(user_id: str, default_data: dict) -> dict:
    """Retrieves profile or creates it if it doesn't exist."""
    profile = get_user_profile(user_id)
    if not profile:
        profile = {
            "name": default_data.get("name", "User"),
            "email": default_data.get("email", ""),
            "photo": default_data.get("picture", ""),
            "createdAt": int(time.time()),
            "onboardingComplete": False
        }
        set_val(f"users/{user_id}/profile", profile)
    return profile


def set_user_languages(user_id: str, languages: list):
    """Sets the user's preferred music languages in user-centric node."""
    # Store as a dict for fast lookup: {lang: true}
    lang_dict = {lang.lower(): True for lang in languages}
    set_val(f"users/{user_id}/languages", lang_dict)
    update(f"users/{user_id}/profile", {"onboardingComplete": True})


def get_user_languages(user_id: str) -> list:
    """Gets user languages as a list."""
    data = get(f"users/{user_id}/languages") or {}
    return list(data.keys())


def follow_artist(user_id: str, artist_id: str, artist_name: str):
    """Follows an artist in the user-centric node with metadata."""
    update(f"users/{user_id}/followed_artists/{artist_id}", {
        "name": artist_name,
        "followedAt": int(time.time())
    })


def get_followed_artists(user_id: str) -> dict:
    """Retrieves the dict of followed artists with metadata."""
    return get(f"users/{user_id}/followed_artists") or {}


# ─── Personalized Recommendations ─────────────────────────────────────────────

def store_recommendations(user_id: str, recommendations: dict):
    """Stores generated recommendations for a user."""
    recommendations["updatedAt"] = int(time.time())
    set_val(f"users/{user_id}/recommendations", recommendations)


def get_stored_recommendations(user_id: str) -> Optional[dict]:
    """Retrieves stored recommendations."""
    return get(f"users/{user_id}/recommendations")
