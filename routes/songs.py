from fastapi import APIRouter, HTTPException, Header
from services.saavn import get_song, slim_song

router = APIRouter()

@router.get("/songs/{id}")
async def song_details(id: str, x_quality: str = Header("medium")):
    """Get details for a specific song with quality optimization."""
    results = get_song(id)
    if isinstance(results, dict) and "data" in results:
        data = results["data"]
        if isinstance(data, list) and len(data) > 0:
            return slim_song(data[0], quality=x_quality)
    raise HTTPException(status_code=404, detail="Song not found")
