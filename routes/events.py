from fastapi import APIRouter, Depends, Query
from middleware.auth import get_current_user
from firebase import db_ops
from pydantic import BaseModel
import threading
from services.saavn import preindex_related

router = APIRouter()

class Event(BaseModel):
    id: str  # songId, etc.
    type: str  # play, like, click

@router.post("/events")
async def record_event(event: Event, user: dict = Depends(get_current_user)):
    """Records user events like play, like, or click."""
    if event.type == "play":
        db_ops.record_play(user["uid"], event.id)
        # Background pre-index related songs to grow the catalog
        threading.Thread(target=preindex_related, args=(event.id,), daemon=True).start()
        return {"status": "success", "event": "play recorded"}
    elif event.type == "like":
        db_ops.record_like(user["uid"], event.id)
        return {"status": "success", "event": "like recorded"}
    elif event.type == "click":
        # Analytics for clicks
        db_ops.record_click(event.id)
        return {"status": "success", "event": "click recorded"}
    
    return {"status": "error", "message": "Unknown event type"}

@router.get("/trending")
async def trending(category: str = Query("daily")):
    """Get trending songs."""
    return db_ops.get_trending(category)

@router.get("/suggestions")
async def suggestions(q: str = Query(..., min_length=1)):
    """Get search suggestions."""
    return db_ops.get_suggestions(q)
