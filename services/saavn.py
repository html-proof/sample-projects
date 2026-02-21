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
    # Check cache first
    cached = db_ops.cache_get(f"all_{query}")
    if cached:
        return {"data": cached, "source": "cache"}
    
    results = _request(f"/api/search?query={_encode(query)}")
    
    # Cache results
    if isinstance(results, dict) and "data" in results:
        db_ops.cache_set(f"all_{query}", results["data"])
        
    return results


def search_songs(query: str, page: int = 1, limit: int = 20) -> dict:
    # Caching only the first page for simplicity
    if page == 1:
        cached = db_ops.cache_get(f"songs_{query}")
        if cached:
            return {"data": {"results": cached}, "source": "cache"}
    
    results = _request(f"/api/search/songs?query={_encode(query)}&page={page}&limit={limit}")
    
    # Cache top results of the first page
    if page == 1 and isinstance(results, dict) and "data" in results:
        data = results["data"]
        if isinstance(data, dict) and "results" in data:
            db_ops.cache_set(f"songs_{query}", data["results"])
            
    return results


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

    return {
        "id":        song.get("id", ""),
        "title":     song.get("name") or song.get("title", ""),
        "artist":    artist_name,
        "album":     (song.get("album") if isinstance(song.get("album"), str) else song.get("album", {}).get("name", "")) or "",
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
