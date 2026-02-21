from fastapi import APIRouter, HTTPException, Header
from services.saavn import get_album_full_details

router = APIRouter()

@router.get("/albums/{id}")
async def album_details(id: str, x_quality: str = Header("medium")):
    """Get full details for an album (metadata and songs)."""
    result = get_album_full_details(id, quality=x_quality)
    if result.get("success"):
        return result
    raise HTTPException(status_code=404, detail=result.get("message", "Album not found"))
