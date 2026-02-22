from fastapi import APIRouter, Query, Depends, Header
from middleware.auth import optional_user
from firebase import db_ops
from services.saavn import (
    search_all, search_songs, slim_song, search_albums, slim_album,
    search_artists, slim_artist, get_album, filter_clean
)

router = APIRouter()


# ─── Spotify-Style Unified Search ─────────────────────────────────────────────

@router.get("/search/all")
async def search_unified(
    query: str = Query(..., min_length=1),
    language: str = Query(None),
    user: dict = Depends(optional_user),
    x_quality: str = Header("medium")
):
    """Spotify-style unified search returning categorized results.
    Returns topResult, songs, albums, and artists in one response."""
    if user:
        db_ops.record_search(user["uid"], query)

    # 1. TRY LOCAL INDEX FIRST (Instant)
    local_songs = db_ops.search_local_index(query, limit=10)
    
    # 2. IF LOCAL RESULTS FOUND, USE THEM (Can still complement with API results in background if needed)
    # For now, if we have local results, we we prioritize them but still fetch other categories
    
    # Fetch songs, albums, and artists from API (cached if possible by saavn.py)
    song_res = search_songs(query, page=1, limit=20, language=language)
    album_res = search_albums(query, page=1, limit=10)
    artist_res = search_artists(query, page=1, limit=10)

    # ── Songs ──
    songs = []
    if isinstance(song_res, dict) and "data" in song_res:
        data = song_res["data"]
        raw = data.get("results", []) if isinstance(data, dict) else []
        songs = [s for s in [slim_song(s, quality=x_quality) for s in filter_clean(raw)] if s.get("streamUrl")]

    # Merge local results into songs (unique IDs)
    if local_songs:
        existing_ids = {s["id"] for s in songs}
        for ls in local_songs:
            if ls["id"] not in existing_ids:
                songs.insert(0, ls) # Prioritize local results at the top

    # ── Albums ──
    albums = []
    if isinstance(album_res, dict) and "data" in album_res:
        data = album_res["data"]
        raw = data.get("results", []) if isinstance(data, dict) else []
        albums = [slim_album(a, quality=x_quality) for a in filter_clean(raw)]

    # ── Artists ──
    artists = []
    if isinstance(artist_res, dict) and "data" in artist_res:
        data = artist_res["data"]
        raw = data.get("results", []) if isinstance(data, dict) else []
        artists = [slim_artist(a, quality=x_quality) for a in raw]

    # ── Top Result ── (best song match)
    top_result = None
    if songs:
        top = songs[0]
        top_result = {**top, "type": "song"}
    elif albums:
        top = albums[0]
        top_result = {**top, "type": "album"}
    elif artists:
        top = artists[0]
        top_result = {**top, "type": "artist"}

    return {
        "success": True,
        "topResult": top_result,
        "songs": songs[:10],
        "albums": albums[:6],
        "artists": artists[:6],
        "totalSongs": len(songs),
        "totalAlbums": len(albums),
        "totalArtists": len(artists),
    }


# ─── Original Endpoints ──────────────────────────────────────────────────────

@router.get("/search")
async def search(
    query: str = Query(..., min_length=1), 
    language: str = Query(None),
    user: dict = Depends(optional_user),
    x_quality: str = Header("medium")
):
    """Search for everything (songs, artists, etc.)."""
    if user:
        db_ops.record_search(user["uid"], query)
    
    results = search_all(query)
    
    # Slim down results based on quality
    if isinstance(results, dict) and "data" in results:
        data = results["data"]
        if "songs" in data and "results" in data["songs"]:
            data["songs"]["results"] = [slim_song(s, quality=x_quality) for s in data["songs"]["results"]]
        if "albums" in data and "results" in data["albums"]:
            data["albums"]["results"] = [slim_album(a, quality=x_quality) for a in data["albums"]["results"]]
        if "artists" in data and "results" in data["artists"]:
            data["artists"]["results"] = [slim_artist(art, quality=x_quality) for art in data["artists"]["results"]]
            
    return results

@router.get("/search/songs")
async def search_for_songs(
    query: str = Query(..., min_length=1), 
    page: int = 1, 
    limit: int = 20,
    language: str = Query(None),
    x_quality: str = Header("medium")
):
    """Search for songs only with quality optimization.
    Also returns the full album of the top result as a recommendation."""
    results = search_songs(query, page, limit, language=language)
    
    recommended_album = None
    
    if isinstance(results, dict) and "data" in results:
        data = results["data"]
        if isinstance(data, dict) and "results" in data:
            data["results"] = [s for s in [slim_song(s, quality=x_quality) for s in filter_clean(data["results"])] if s.get("streamUrl")]
            
            # Extract album from the TOP result for recommendation
            if page == 1 and data["results"]:
                top_song = data["results"][0]
                album_id = top_song.get("albumId", "")
                
                if album_id:
                    try:
                        album_data = get_album(album_id)
                        if isinstance(album_data, dict) and "data" in album_data:
                            album_raw = album_data["data"]
                            album_songs = album_raw.get("songs", [])
                            recommended_album = {
                                "id": album_raw.get("id", ""),
                                "name": album_raw.get("name", ""),
                                "image": slim_album(album_raw).get("image", ""),
                                "artist": slim_album(album_raw).get("artist", ""),
                                "year": album_raw.get("year", ""),
                                "songCount": len(album_songs),
                                "songs": [slim_song(s, quality=x_quality) for s in album_songs],
                            }
                    except Exception as e:
                        print(f"Album fetch error: {e}")
    
    if recommended_album:
        results["recommended_album"] = recommended_album
    
    # Strip internal fields before sending to client
    results.pop("_raw_results", None)
        
    return results

@router.get("/search/albums")
async def search_for_albums(
    query: str = Query(..., min_length=1), 
    page: int = 1, 
    limit: int = 10,
    x_quality: str = Header("medium")
):
    """Search for albums only."""
    results = search_albums(query, page, limit)
    
    if isinstance(results, dict) and "data" in results:
        data = results["data"]
        if isinstance(data, dict) and "results" in data:
            data["results"] = [slim_album(a, quality=x_quality) for a in filter_clean(data["results"])]
    return results
