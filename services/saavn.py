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
    
    # Store in metadata cache
    if isinstance(results, dict) and "data" in results:
        data = results["data"]
        if isinstance(data, list) and len(data) > 0:
            db_ops.song_set(song_id, slim_song(data[0]))
            
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

def slim_song(song: dict) -> dict:
    """Return minimal song data for mobile-friendly responses."""
    image = song.get("image", [])
    small_img = image[0].get("url", "") if image else ""
    download = song.get("downloadUrl", [])
    stream_url = download[-1].get("url", "") if download else ""

    return {
        "id":        song.get("id", ""),
        "title":     song.get("name", ""),
        "artist":    ", ".join(a.get("name", "") for a in song.get("artists", {}).get("primary", [])),
        "album":     song.get("album", {}).get("name", ""),
        "image":     small_img,
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

def get_top_artists_by_language(languages: list, limit: int = 10) -> list:
    """Fetches top artists for a list of languages."""
    # Since Saavn doesn't have a direct 'top artists by language' API, 
    # we can search for 'Top {Language} Artists' or specific charts.
    # For now, we'll use a search-based approach for each language.
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
