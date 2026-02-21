from fastapi import APIRouter, Depends, HTTPException, Query
from middleware.auth import get_current_user
from firebase import db_ops
from services.saavn import get_top_artists_by_language
from pydantic import BaseModel
from typing import List

router = APIRouter()

class LanguagesInput(BaseModel):
    languages: List[str]

class FollowArtistInput(BaseModel):
    artistId: str
    artistName: str

@router.post("/onboarding/languages")
async def select_languages(data: LanguagesInput, user: dict = Depends(get_current_user)):
    """Saves the user's preferred music languages."""
    db_ops.set_user_languages(user["uid"], data.languages)
    return {"status": "success", "message": "Languages saved"}

@router.get("/onboarding/artists")
async def get_onboarding_artists(user: dict = Depends(get_current_user)):
    """Fetches artists based on the user's selected languages for discovery."""
    languages = db_ops.get_user_languages(user["uid"])
    
    if not languages:
        raise HTTPException(status_code=400, detail="Please select languages first")
    
    artists = get_top_artists_by_language(languages)
    return {"artists": artists}

@router.post("/onboarding/follow")
async def follow_artist(data: FollowArtistInput, user: dict = Depends(get_current_user)):
    """Follows an artist during or after onboarding."""
    db_ops.follow_artist(user["uid"], data.artistId, data.artistName)
    return {"status": "success", "message": f"Followed {data.artistName}"}
