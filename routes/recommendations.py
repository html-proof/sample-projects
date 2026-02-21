from fastapi import APIRouter, Query, Depends
from recommender.engine import (
    get_recommendations, build_smart_queue,
    generate_daily_mix, get_trending_songs
)
from middleware.auth import get_current_user, optional_user

router = APIRouter()


@router.get("/recommendations")
async def recommendations(
    currentSong: str = Query(None),
    limit: int = Query(20, le=50),
    user=Depends(get_current_user)
):
    result = get_recommendations(user["uid"], current_song_id=currentSong, limit=limit)
    return result


@router.get("/queue/smart")
async def smart_queue(
    seedSong: str = Query(...),
    size: int = Query(15, le=30),
    user=Depends(get_current_user)
):
    queue = build_smart_queue(user["uid"], seedSong, queue_size=size)
    return {"queue": queue, "size": len(queue)}


@router.get("/mix/daily")
async def daily_mix(user=Depends(get_current_user)):
    mix = generate_daily_mix(user["uid"])
    return {"mix": mix, "count": len(mix)}


@router.get("/trending")
async def trending(limit: int = Query(20, le=50), user=Depends(optional_user)):
    songs = get_trending_songs(limit=limit)
    return {"trending": songs}
