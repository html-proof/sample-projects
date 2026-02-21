from fastapi import APIRouter, HTTPException
from services.saavn import get_song, slim_song

router = APIRouter()

@router.get("/songs/{id}")
async def song_details(id: str):
    """Get details for a specific song."""
    results = get_song(id)
    if results.get("source") == "cache":
        return results["data"][0]
    
    if isinstance(results, dict) and "data" in results:
        data = results["data"]
        if isinstance(data, list) and len(data) > 0:
            return slim_song(data[0])
    raise HTTPException(status_code=404, detail="Song not found")
