from fastapi import APIRouter, Query, Depends, Header
from middleware.auth import optional_user
from firebase import db_ops
from services.saavn import search_all, search_songs, slim_song, search_albums, slim_album, get_album

router = APIRouter()

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
    return search_all(query)

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
            data["results"] = [slim_song(s, quality=x_quality) for s in data["results"]]
            
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
    limit: int = 10
):
    """Search for albums only."""
    results = search_albums(query, page, limit)
    
    if isinstance(results, dict) and "data" in results:
        data = results["data"]
        if isinstance(data, dict) and "results" in data:
            data["results"] = [slim_album(a) for a in data["results"]]
    return results
