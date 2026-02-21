from fastapi import APIRouter, Query, Depends
from middleware.auth import optional_user
from firebase import db_ops

router = APIRouter()

@router.get("/search")
async def search(q: str = Query(..., min_length=1), user: dict = Depends(optional_user)):
    """Search for everything (songs, albums, artists, etc.)."""
    if user:
        db_ops.record_search(user["uid"], q)
    return search_all(q)

@router.get("/search/songs")
async def search_for_songs(q: str = Query(..., min_length=1), page: int = 1, limit: int = 20):
    """Search for songs only."""
    results = search_songs(q, page, limit)
    
    if results.get("source") == "cache":
        return results
    
    # The Saavn API response contains a "data" or "results" key depending on version/endpoint
    if isinstance(results, dict) and "data" in results:
        data = results["data"]
        if isinstance(data, dict) and "results" in data:
            data["results"] = [slim_song(s) for s in data["results"]]
    return results
