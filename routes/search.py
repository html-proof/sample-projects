from fastapi import APIRouter, Query, Depends, Header
from middleware.auth import optional_user
from firebase import db_ops
from services.saavn import search_all, search_songs, slim_song

router = APIRouter()

@router.get("/search")
async def search(
    q: str = Query(..., min_length=1), 
    user: dict = Depends(optional_user),
    x_quality: str = Header("medium")
):
    """Search for everything (songs, artists, etc.)."""
    if user:
        db_ops.record_search(user["uid"], q)
    return search_all(q)

@router.get("/search/songs")
async def search_for_songs(
    q: str = Query(..., min_length=1), 
    page: int = 1, 
    limit: int = 20,
    x_quality: str = Header("medium")
):
    """Search for songs only with quality optimization."""
    results = search_songs(q, page, limit)
    
    if results.get("source") == "cache":
        return results
    
    if isinstance(results, dict) and "data" in results:
        data = results["data"]
        if isinstance(data, dict) and "results" in data:
            data["results"] = [slim_song(s, quality=x_quality) for s in data["results"]]
    return results
