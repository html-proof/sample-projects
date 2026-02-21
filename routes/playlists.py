from fastapi import Header, APIRouter, Depends, Query, HTTPException
from middleware.auth import get_current_user
from firebase import db_ops
from services.saavn import get_playlist as get_saavn_playlist, slim_song
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

class PlaylistCreate(BaseModel):
    name: str

class PlaylistAddSong(BaseModel):
    songId: str

@router.post("/playlists")
async def create_playlist(data: PlaylistCreate, user: dict = Depends(get_current_user)):
    """Creates a new playlist."""
    playlist_id = db_ops.playlist_create(user["uid"], data.name)
    return {"status": "success", "playlistId": playlist_id}

@router.get("/playlists")
async def list_playlists(user: dict = Depends(get_current_user)):
    """Lists all playlists for the current user."""
    return db_ops.get_user_playlists(user["uid"])

@router.get("/playlists/{id}")
async def get_playlist(id: str):
    """Gets details for a specific playlist."""
    playlist = db_ops.playlist_get(id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return playlist

@router.post("/playlists/{id}/songs")
async def add_to_playlist(id: str, data: PlaylistAddSong, user: dict = Depends(get_current_user)):
    """Adds a song to a playlist."""
    playlist = db_ops.playlist_get(id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    if playlist.get("owner") != user["uid"]:
        raise HTTPException(status_code=403, detail="You do not own this playlist")
    
    db_ops.playlist_add_song(id, data.songId)
    return {"status": "success", "message": "Song added to playlist"}

@router.get("/playlists/{id}/songs")
async def playlist_songs(id: str, x_quality: str = Header("medium")):
    """Gets songs for a specific playlist (user or Saavn)."""
    # 1. Try User Playlist
    playlist = db_ops.playlist_get(id)
    if playlist:
        songs = db_ops.playlist_get_songs(id)
        return {
            "name": playlist.get("name"),
            "songs": [slim_song(s, quality=x_quality) for s in songs]
        }
    
    # 2. Try Saavn Playlist
    try:
        res = get_saavn_playlist(id)
        if res and "data" in res:
            data = res["data"]
            return {
                "name": data.get("name"),
                "image": data.get("image", [{}])[-1].get("url", ""),
                "songs": [slim_song(s, quality=x_quality) for s in data.get("songs", [])]
            }
    except:
        pass
        
    raise HTTPException(status_code=404, detail="Playlist not found")
