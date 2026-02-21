import http.client
import json
import urllib.parse
from services.saavn import _decrypt_url, JIOSAAVN_DES_KEY

def get_lyrics(song_id: str) -> dict:
    """Fetch lyrics for a song from JioSaavn."""
    try:
        conn = http.client.HTTPSConnection("www.jiosaavn.com", timeout=8)
        params = urllib.parse.urlencode({
            "__call": "lyrics.getLyrics",
            "_format": "json",
            "ctx": "web6dot0",
            "api_version": "4",
            "lyrics_id": song_id,
        })
        conn.request("GET", f"/api.php?{params}", headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        res = conn.getresponse()
        raw = res.read().decode("utf-8")
        conn.close()
        
        data = json.loads(raw)
        if "lyrics" in data:
            # Unescape some common HTML entities if present
            lyrics_text = data["lyrics"].replace("<br />", "\n").replace("<br/>", "\n")
            return {"success": True, "lyrics": lyrics_text}
        
        return {"success": False, "message": "Lyrics not found"}
        
    except Exception as e:
        print(f"Lyrics fetch error: {e}")
        return {"success": False, "message": str(e)}
