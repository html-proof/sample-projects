import http.client
import json
import urllib.parse
from typing import Optional
import os
from firebase import db_ops

SAAVN_HOST = os.getenv("SAAVN_HOST", "saavn.sumit.co")


def _request(path: str) -> dict:
    conn = http.client.HTTPSConnection(SAAVN_HOST)
    conn.request("GET", path, headers={"Accept": "application/json"})
    res = conn.getresponse()
    raw = res.read().decode("utf-8")
    conn.close()
    return json.loads(raw)


def _encode(q: str) -> str:
    return urllib.parse.quote(q)


# ─── Search ───────────────────────────────────────────────────────────────────

def search_all(query: str) -> dict:
    # Use generic cache (not the song-specific deep cache)
    cached = db_ops.generic_cache_get("search_all_cache", query, ttl_seconds=3600)
    if cached:
        return {"data": cached, "source": "cache"}
    
    results = _request(f"/api/search?query={_encode(query)}")
    
    # Cache results using generic cache
    if isinstance(results, dict) and "data" in results:
        db_ops.generic_cache_set("search_all_cache", query, results["data"])
        
    return results


def search_songs(query: str, page: int = 1, limit: int = 20) -> dict:
    # 1. ALWAYS check the deep cache index first
    if page == 1:
        cached_results = db_ops.cache_get(query)
        if cached_results:
            return {"data": {"results": cached_results}, "source": "cache"}
            
    # Helper to execute query against API
    def _fetch(q: str) -> list:
        try:
            res = _request(f"/api/search/songs?query={_encode(q)}&page={page}&limit={limit}")
            if isinstance(res, dict) and "data" in res:
                data = res["data"]
                if isinstance(data, dict) and "results" in data:
                    return data["results"]
        except Exception:
            pass
        return []

    # 2. Try Exact Query
    results = _fetch(query)
    
    # 3. Fallback / Query Expansion
    if not results and page == 1:
        parts = query.split()
        if len(parts) > 1:
            # Strategy A: try just the first word (likely the song title)
            results = _fetch(parts[0])
            
            # Strategy B: try reversed order ("imagine dragons believer" -> "believer imagine dragons")
            if not results:
                results = _fetch(" ".join(reversed(parts)))
            
            # Strategy C: try each word individually and merge
            if not results:
                for word in parts:
                    if len(word) > 2:  # skip short noise words
                        results = _fetch(word)
                        if results:
                            break

    # 4. Deep Cache Store
    if page == 1 and results:
        db_ops.cache_set(query, results)
        
    return {
        "success": True,
        "data": {
            "start": (page - 1) * limit,
            "total": len(results),
            "results": results
        },
        "_raw_results": results  # Pass raw data for album extraction in route
    }


def search_albums(query: str, page: int = 1, limit: int = 10) -> dict:
    return _request(f"/api/search/albums?query={_encode(query)}&page={page}&limit={limit}")


def search_artists(query: str, page: int = 1, limit: int = 10) -> dict:
    return _request(f"/api/search/artists?query={_encode(query)}&page={page}&limit={limit}")


def search_playlists(query: str, page: int = 1, limit: int = 10) -> dict:
    return _request(f"/api/search/playlists?query={_encode(query)}&page={page}&limit={limit}")


# ─── Songs ────────────────────────────────────────────────────────────────────

def get_song(song_id: str) -> dict:
    # Check cache first
    cached = db_ops.song_get(song_id)
    if cached:
        return {"data": [cached], "source": "cache"}
    
    results = _request(f"/api/songs/{song_id}")
    
    # Store in metadata cache - STORE RAW DATA for maximum flexibility
    if isinstance(results, dict) and "data" in results:
        data = results["data"]
        if isinstance(data, list) and len(data) > 0:
            db_ops.song_set(song_id, data[0]) # Store raw
            
    return results


def get_song_suggestions(song_id: str, limit: int = 10) -> dict:
    return _request(f"/api/songs/{song_id}/suggestions?limit={limit}")


# ─── Albums ───────────────────────────────────────────────────────────────────

def get_album(album_id: str) -> dict:
    return _request(f"/api/albums?id={album_id}")


# ─── Artists ──────────────────────────────────────────────────────────────────

def get_artist(artist_id: str) -> dict:
    return _request(f"/api/artists/{artist_id}")


def get_artist_songs(artist_id: str, page: int = 0, sort: str = "latest") -> dict:
    return _request(f"/api/artists/{artist_id}/songs?page={page}&sortBy={sort}")


def get_artist_albums(artist_id: str, page: int = 0, sort: str = "latest") -> dict:
    return _request(f"/api/artists/{artist_id}/albums?page={page}&sortBy={sort}")


# ─── Playlists ────────────────────────────────────────────────────────────────

def get_playlist(playlist_id: str, page: int = 1) -> dict:
    return _request(f"/api/playlists?id={playlist_id}&page={page}")


# ─── Data Transformation ─────────────────────────────────────────────────────

def slim_song(song: dict, quality: str = "medium") -> dict:
    """Return minimal song data for mobile-friendly responses.
    quality: 'low', 'medium', 'high'
    """
    # If already slimmed, return as is (idempotency)
    if "title" in song and "imageUrl" not in song and "image" in song and isinstance(song["image"], str):
        return song

    image_data = song.get("image")
    # Handle if it's already a flat string or a list of maps
    if isinstance(image_data, list) and image_data:
        # Low: smallest image, High: largest image
        if quality == "low":
            img = image_data[0].get("url", "") if image_data else ""
        elif quality == "high":
            img = image_data[-1].get("url", "") if image_data else ""
        else:
            img = image_data[1].get("url", "") if len(image_data) > 1 else (image_data[0].get("url", "") if image_data else "")
    elif isinstance(image_data, str):
        img = image_data
    else:
        img = ""

    downloads = song.get("downloadUrl", [])
    if isinstance(downloads, list) and downloads:
        # bitrates: 0=12kbps, 1=48kbps, 2=96kbps, 3=160kbps, 4=320kbps (approx)
        if quality == "low":
            stream_url = downloads[1].get("url", "") if len(downloads) > 1 else (downloads[0].get("url", "") if downloads else "")
        elif quality == "high":
            stream_url = downloads[-1].get("url", "") if downloads else ""
        else:
            stream_url = downloads[2].get("url", "") if len(downloads) > 2 else (downloads[-1].get("url", "") if downloads else "")
    elif isinstance(song.get("streamUrl"), str):
        stream_url = song.get("streamUrl", "")
    else:
        stream_url = ""

    # Force aac.saavncdn.com CDN
    if stream_url and "saavncdn.com" in stream_url:
        parts = stream_url.split("saavncdn.com/", 1)
        if len(parts) > 1:
            stream_url = "https://aac.saavncdn.com/" + parts[1]

    # Handle artist extraction robustly
    artist_data = song.get("artists", {})
    if isinstance(artist_data, dict) and "primary" in artist_data:
        artist_name = ", ".join(a.get("name", "") for a in artist_data.get("primary", []))
    elif isinstance(song.get("artist"), str):
        artist_name = song.get("artist", "")
    else:
        artist_name = "Unknown Artist"

    # Extract album name and ID
    album_raw = song.get("album", {})
    if isinstance(album_raw, dict):
        album_name = album_raw.get("name", "")
        album_id = album_raw.get("id", "")
    elif isinstance(album_raw, str):
        album_name = album_raw
        album_id = song.get("albumId", "")
    else:
        album_name = ""
        album_id = ""

    return {
        "id":        song.get("id", ""),
        "title":     song.get("name") or song.get("title", ""),
        "artist":    artist_name,
        "album":     album_name,
        "albumId":   album_id,
        "image":     img,
        "duration":  song.get("duration", 0),
        "language":  song.get("language", ""),
        "year":      song.get("year", ""),
        "streamUrl": stream_url,
    }


def slim_artist(artist: dict) -> dict:
    image = artist.get("image", [])
    img = image[-1].get("url", "") if image else ""
    return {
        "id":       artist.get("id", ""),
        "name":     artist.get("name", ""),
        "image":    img,
        "follower": artist.get("followerCount", 0),
        "url":      artist.get("url", ""),
    }


def slim_album(album: dict) -> dict:
    image = album.get("image", [])
    img = image[-1].get("url", "") if image else ""
    artist_data = album.get("artists", {}).get("primary", [])
    artist_name = ", ".join(a.get("name", "") for a in artist_data) if artist_data else ""
    
    return {
        "id":        album.get("id", ""),
        "name":      album.get("name", ""),
        "image":     img,
        "artist":    artist_name,
        "language":  album.get("language", ""),
        "year":      album.get("year", ""),
    }


# ─── Language Discovery ───────────────────────────────────────────────────────

def get_top_artists_by_language(languages: list = None, limit: int = 10) -> list:
    """Fetches top artists for a list of languages. Defaults to English/Hindi if none provided."""
    languages = languages or ["english", "hindi"]
    all_artists = []
    seen_ids = set()
    
    for lang in languages:
        try:
            # Search for the language and extract artists
            results = search_artists(lang, limit=limit)
            if isinstance(results, dict) and "data" in results:
                data = results["data"]
                if isinstance(data, dict) and "results" in data:
                    for artist in data["results"]:
                        slim = slim_artist(artist)
                        if slim["id"] not in seen_ids:
                            all_artists.append(slim)
                            seen_ids.add(slim["id"])
        except Exception:
            continue
            
    return all_artists

def get_trending_fallback(quality: str = "medium", limit: int = 10) -> list:
    """Fetch globally popular songs from Saavn search as a fallback."""
    try:
        raw = search_songs("trending hits", page=1, limit=limit)
        if isinstance(raw, dict) and "data" in raw:
            data = raw["data"]
            results = data.get("results", []) if isinstance(data, dict) else []
            return [slim_song(s, quality=quality) for s in results[:limit]]
    except:
        pass
    return []


# ─── Pre-Indexing (Background Catalog Building) ──────────────────────────────

def preindex_related(song_id: str):
    """When a song is played, cache its suggestions and artist tracks.
    This organically grows the searchable catalog over time.
    Called in a background thread so it doesn't block playback.
    """
    try:
        # 1. Cache song suggestions (related songs)
        suggestions = get_song_suggestions(song_id, limit=10)
        if isinstance(suggestions, dict) and "data" in suggestions:
            for s in suggestions["data"]:
                if isinstance(s, dict) and s.get("id"):
                    db_ops.song_set(s["id"], s)

        # 2. Get the song itself to find its artist
        song_data = get_song(song_id)
        if isinstance(song_data, dict) and "data" in song_data:
            songs_list = song_data["data"]
            if isinstance(songs_list, list) and songs_list:
                song = songs_list[0]
                # Extract artist IDs
                artists = song.get("artists", {})
                primary = artists.get("primary", []) if isinstance(artists, dict) else []
                for artist in primary[:2]:  # Limit to first 2 artists
                    artist_id = artist.get("id")
                    if artist_id:
                        # Cache their top songs
                        artist_songs = get_artist_songs(artist_id, page=0)
                        if isinstance(artist_songs, dict) and "data" in artist_songs:
                            a_data = artist_songs["data"]
                            a_songs = a_data.get("songs", []) if isinstance(a_data, dict) else []
                            for as_item in a_songs[:10]:
                                if isinstance(as_item, dict) and as_item.get("id"):
                                    db_ops.song_set(as_item["id"], as_item)
    except Exception as e:
        print(f"Pre-indexing error (non-critical): {e}")

