import http.client
import json
import html
import urllib.parse
from typing import Optional
import os
import base64
import gzip
import io
from firebase import db_ops

SAAVN_HOST = os.getenv("SAAVN_HOST", "saavn.sumit.co")
JIOSAAVN_DES_KEY = b"38346591"  # JioSaavn's known DES key for URL decryption


def is_url_reachable(url: str) -> bool:
    """Check if a URL is reachable (returns 200 or 206 for media)."""
    if not url:
        return False
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme == "https":
            conn = http.client.HTTPSConnection(parsed.netloc, timeout=3)
        else:
            conn = http.client.HTTPConnection(parsed.netloc, timeout=3)
            
        conn.request("HEAD", parsed.path + ("?" + parsed.query if parsed.query else ""))
        res = conn.getresponse()
        conn.close()
        # 200 OK or 206 Partial Content (common for streaming)
        return res.status in (200, 206)
    except Exception as e:
        print(f"URL reachability check failed for {url}: {e}")
        return False


def _request(path: str) -> dict:
    conn = http.client.HTTPSConnection(SAAVN_HOST)
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip"
    }
    conn.request("GET", path, headers=headers)
    res = conn.getresponse()
    
    encoding = res.getheader("Content-Encoding")
    raw_data = res.read()
    
    if encoding == "gzip":
        with gzip.GzipFile(fileobj=io.BytesIO(raw_data)) as f:
            data = f.read().decode("utf-8")
    else:
        data = raw_data.decode("utf-8")
        
    conn.close()
    return json.loads(data)


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


# ─── JioSaavn Direct API (Fallback) ──────────────────────────────────────────

def _decrypt_url(encrypted_url: str) -> str:
    """Decrypt JioSaavn's encrypted media URL using DES-ECB."""
    try:
        from Crypto.Cipher import DES
        cipher = DES.new(JIOSAAVN_DES_KEY, DES.MODE_ECB)
        encrypted_data = base64.b64decode(encrypted_url.strip())
        decrypted = cipher.decrypt(encrypted_data)
        return decrypted.decode("utf-8").strip("\x00\x01\x02\x03\x04\x05\x06\x07\x08")
    except Exception as e:
        print(f"DES decrypt error: {e}")
        return ""


def _search_jiosaavn_direct(query: str, limit: int = 10) -> list:
    """Fallback: search JioSaavn's internal api.php directly."""
    try:
        conn = http.client.HTTPSConnection("www.jiosaavn.com", timeout=8)
        params = urllib.parse.urlencode({
            "__call": "search.getResults",
            "_format": "json",
            "_marker": "0",
            "api_version": "3",
            "ctx": "wap6dot0",
            "n": str(limit),
            "p": "1",
            "q": query,
        })
        conn.request("GET", f"/api.php?{params}", headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        res = conn.getresponse()
        raw = res.read().decode("utf-8")
        conn.close()
        
        data = json.loads(raw)
        results_list = data.get("results", [])
        
        songs = []
        for item in results_list:
            # Decrypt the encrypted media URL
            encrypted = item.get("encrypted_media_url", "")
            stream_url = _decrypt_url(encrypted) if encrypted else ""
            
            # Force bitrates based on "quality" if we had it here, 
            # but usually direct search is called for a specific query.
            # We'll default to 320 for the cache, and slim_song will downgrade later.
            if stream_url and "_96." in stream_url:
                stream_url = stream_url.replace("_96.", "_320.")
            elif stream_url and "_160." in stream_url:
                stream_url = stream_url.replace("_160.", "_320.")
            
            # Force aac.saavncdn.com CDN
            if stream_url and "saavncdn.com" in stream_url:
                parts = stream_url.split("saavncdn.com/", 1)
                if len(parts) > 1:
                    stream_url = "https://aac.saavncdn.com/" + parts[1]
                    
            # Build image URL - keep original 500x500 for storage
            image = item.get("image", "")
            if isinstance(image, str) and image:
                image = image.replace("150x150", "500x500").replace("50x50", "500x500")
            
            # Get artist names
            primary_artists = item.get("primary_artists", item.get("singers", ""))
            
            # Get album info
            album_name = item.get("album", "")
            album_id = item.get("albumid", "")
            
            song = {
                "id": item.get("id", ""),
                "name": html.unescape(item.get("song", item.get("title", ""))),
                "title": html.unescape(item.get("song", item.get("title", ""))),
                "artist": html.unescape(primary_artists),
                "album": html.unescape(album_name),
                "albumId": album_id,
                "image": image,
                "duration": int(item.get("duration", 0) or 0),
                "language": item.get("language", ""),
                "year": item.get("year", ""),
                "streamUrl": stream_url,
            }
            
            if song["id"] and song["name"]:
                songs.append(song)
        
        if songs:
            print(f"JioSaavn direct: found {len(songs)} songs for '{query}'")
        return songs
        
    except Exception as e:
        print(f"JioSaavn direct fallback error: {e}")
        return []

def search_songs(query: str, page: int = 1, limit: int = 20, language: str = None) -> dict:
    # 1. ALWAYS check the deep cache index first
    cache_key = f"{query}_{language}" if language else query
    if page == 1:
        cached_results = db_ops.cache_get(cache_key)
        if cached_results:
            return {"data": {"results": cached_results}, "source": "cache"}
            
    # Helper to execute query against API
    lang_param = f"&language={_encode(language)}" if language else ""
    def _fetch(q: str) -> list:
        try:
            res = _request(f"/api/search/songs?query={_encode(q)}&page={page}&limit={limit}{lang_param}")
            if isinstance(res, dict) and "data" in res:
                data = res["data"]
                if isinstance(data, dict) and "results" in data:
                    return data["results"]
        except Exception:
            pass
        return []

    # 2. Try Direct JioSaavn API first (Official internal API, most reliable)
    if page == 1:
        direct_results = _search_jiosaavn_direct(query, limit=limit)
        if direct_results:
            results = direct_results

    # 3. Fallback: Try the unofficial API wrapper if direct failed or for pagination
    if not results or page > 1:
        results = _fetch(query)
    
    # 4. Fallback / Query Expansion (if everything else failed)
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
        db_ops.cache_set(cache_key, results)
        
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

def get_song(song_id: str, refresh: bool = False) -> dict:
    # Check cache first unless refresh is forced
    if not refresh:
        cached = db_ops.song_get(song_id)
        if cached:
            # Check if the cached URL is still reachable
            stream_url = cached.get("streamUrl")
            if stream_url and is_url_reachable(stream_url):
                return {"data": [cached], "source": "cache"}
            else:
                print(f"Cached URL for {song_id} is dead or missing, refreshing...")
    
    results = _request(f"/api/songs/{song_id}")
    
    # Store in metadata cache - STORE RAW DATA for maximum flexibility
    if isinstance(results, dict) and "data" in results:
        data = results["data"]
        if isinstance(data, list) and len(data) > 0:
            song_to_cache = data[0]
            # Ensure the stream URL is actually valid before caching
            stream_url = song_to_cache.get("streamUrl")
            # If the API returned a dead link, don't pollute our cache with it
            if stream_url and is_url_reachable(stream_url):
                db_ops.song_set(song_id, song_to_cache)
            else:
                 print(f"API returned dead/invalid URL for {song_id}, skipping cache.")
            
    return results


def get_song_suggestions(song_id: str, limit: int = 10) -> dict:
    return _request(f"/api/songs/{song_id}/suggestions?limit={limit}")


# ─── Albums ───────────────────────────────────────────────────────────────────

def get_album(album_id: str) -> dict:
    return _request(f"/api/albums?id={album_id}")


# ─── Artists ──────────────────────────────────────────────────────────────────

def get_artist(artist_id: str) -> dict:
    return _request(f"/api/artists/{artist_id}")

def get_artist_full_details(artist_id: str, quality: str = "medium") -> dict:
    """Fetch artist bio, top songs, and albums and slim them."""
    try:
        # Fetch base artist info
        raw_artist = get_artist(artist_id)
        if not raw_artist or not raw_artist.get("data"):
            return {"success": False, "message": "Artist not found"}
        
        artist_data = raw_artist["data"]
        slimmed_artist = slim_artist(artist_data, quality=quality)
        
        # Add bio/description if available
        slimmed_artist["bio"] = artist_data.get("description", "") or artist_data.get("bio", "")
        
        # Fetch top songs
        raw_songs = get_artist_songs(artist_id)
        songs = []
        if raw_songs and "data" in raw_songs and "songs" in raw_songs["data"]:
            songs = [slim_song(s, quality=quality) for s in raw_songs["data"]["songs"]]
            
        # Fetch albums
        raw_albums = get_artist_albums(artist_id)
        albums = []
        if raw_albums and "data" in raw_albums and "albums" in raw_albums["data"]:
            albums = [slim_album(a, quality=quality) for a in raw_albums["data"]["albums"]]
            
        return {
            "success": True,
            "artist": slimmed_artist,
            "songs": songs[:20],  # Top 20 songs
            "albums": albums[:10]   # Top 10 albums
        }
    except Exception as e:
        print(f"Error fetching artist full details: {e}")
        return {"success": False, "message": str(e)}

def get_album_full_details(album_id: str, quality: str = "medium") -> dict:
    """Fetch album info and its songs."""
    try:
        raw_album = get_album(album_id)
        if not raw_album or not raw_album.get("data"):
            return {"success": False, "message": "Album not found"}
            
        album_data = raw_album["data"]
        slimmed_album = slim_album(album_data, quality=quality)
        
        # Extract songs - they are often inside the album data in JioSaavn API
        songs_raw = album_data.get("songs", [])
        songs = [slim_song(s, quality=quality) for s in songs_raw]
        
        return {
            "success": True,
            "album": slimmed_album,
            "songs": songs
        }
    except Exception as e:
        print(f"Error fetching album full details: {e}")
        return {"success": False, "message": str(e)}


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

    # Dynamic Image Sizing: If quality is low, use 150x150 instead of 500x500
    if img and quality == "low":
        img = img.replace("500x500", "150x150")
    elif img and (quality == "medium" or quality == "high"):
        img = img.replace("150x150", "500x500")

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

    # Force aac.saavncdn.com CDN and ensure it's not a dummy .jpg link (sometimes happens in raw data)
    if stream_url and "saavncdn.com" in stream_url:
        if stream_url.endswith(".jpg") or stream_url.endswith(".png"):
            stream_url = "" # Invalid stream
        else:
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
        "title":     html.unescape(song.get("name") or song.get("title", "")),
        "artist":    html.unescape(artist_name),
        "album":     html.unescape(album_name),
        "albumId":   album_id,
        "image":     img,
        "duration":  song.get("duration", 0),
        "language":  song.get("language", ""),
        "year":      song.get("year", ""),
        "streamUrl": stream_url,
    }


def slim_artist(artist: dict, quality: str = "medium") -> dict:
    image = artist.get("image", [])
    img = image[-1].get("url", "") if image else ""
    
    # Dynamic Image Sizing
    if img and quality == "low":
        img = img.replace("500x500", "150x150").replace("450x450", "150x150")
    elif img and (quality == "medium" or quality == "high"):
        img = img.replace("150x150", "500x500").replace("50x50", "500x500")

    return {
        "id":       artist.get("id", ""),
        "name":     html.unescape(artist.get("name", "")),
        "image":    img,
        "follower": artist.get("followerCount", 0),
        "url":      artist.get("url", ""),
    }


def slim_album(album: dict, quality: str = "medium") -> dict:
    image = album.get("image", [])
    img = image[-1].get("url", "") if image else ""
    artist_data = album.get("artists", {}).get("primary", [])
    artist_name = ", ".join(a.get("name", "") for a in artist_data) if artist_data else ""
    
    # Dynamic Image Sizing
    if img and quality == "low":
        img = img.replace("500x500", "150x150").replace("450x450", "150x150")
    elif img and (quality == "medium" or quality == "high"):
        img = img.replace("150x150", "500x500").replace("50x50", "500x500")

    return {
        "id":        album.get("id", ""),
        "name":      html.unescape(album.get("name", "")),
        "image":     img,
        "artist":    html.unescape(artist_name),
        "language":  album.get("language", ""),
        "year":      album.get("year", ""),
    }


# ─── Language Discovery ───────────────────────────────────────────────────────

def get_top_artists_by_language(languages: list = None, limit: int = 10, quality: str = "medium") -> list:
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
                        slim = slim_artist(artist, quality=quality)
                        if slim["id"] not in seen_ids:
                            all_artists.append(slim)
                            seen_ids.add(slim["id"])
        except Exception:
            continue
            
    return all_artists

def get_trending_fallback(quality: str = "medium", limit: int = 10) -> list:
    """Fetch globally popular songs from Saavn search as a fallback."""
    try:
        # Pass quality to search_songs if needed, but search_songs already returns raw, 
        # so we slim them individually below.
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

