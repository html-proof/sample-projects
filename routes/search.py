from fastapi import APIRouter, Query, Depends, Header
from middleware.auth import optional_user
from firebase import db_ops
from services.saavn import search_all, search_songs, slim_song, search_albums, slim_album

router = APIRouter()

@router.get("/search")
async def search(
    query: str = Query(..., min_length=1), 
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
    x_quality: str = Header("medium")
):
    """Search for songs only with quality optimization."""
    results = search_songs(query, page, limit)
    
    if isinstance(results, dict) and "data" in results:
        data = results["data"]
        if isinstance(data, dict) and "results" in data:
            data["results"] = [slim_song(s, quality=x_quality) for s in data["results"]]
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
