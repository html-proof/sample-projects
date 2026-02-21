from fastapi import APIRouter, HTTPException, Header
from services.saavn import get_artist_full_details

router = APIRouter()

@router.get("/artists/{id}")
async def artist_details(id: str, x_quality: str = Header("medium")):
    """Get full details for an artist (bio, songs, albums)."""
    result = get_artist_full_details(id, quality=x_quality)
    if result.get("success"):
        return result
    raise HTTPException(status_code=404, detail=result.get("message", "Artist not found"))
