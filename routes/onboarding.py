from fastapi import APIRouter, Depends, HTTPException, Query, Header
from middleware.auth import get_current_user
from firebase import db_ops
from services.saavn import get_top_artists_by_language
from pydantic import BaseModel
from typing import List

router = APIRouter()

# ─── Master Language List (24 Indian Languages) ──────────────────────────────

MASTER_LANGUAGES = [
    {"code": "hi", "name": "Hindi",      "native": "हिन्दी",    "image": "https://images.unsplash.com/photo-1532375810709-75b1da00537c?w=400&q=80"},
    {"code": "en", "name": "English",    "native": "English",   "image": "https://images.unsplash.com/photo-1449034446853-66c86144b0ad?w=400&q=80"},
    {"code": "ta", "name": "Tamil",      "native": "தமிழ்",      "image": "https://images.unsplash.com/photo-1582510003544-4d00b7f74220?w=400&q=80"},
    {"code": "te", "name": "Telugu",     "native": "తెలుగు",     "image": "https://images.unsplash.com/photo-1605141258169-42b71457fb1e?w=400&q=80"},
    {"code": "ml", "name": "Malayalam",  "native": "മലയാളം",    "image": "https://images.unsplash.com/photo-1602216056096-3b40cc0c9944?w=400&q=80"},
    {"code": "kn", "name": "Kannada",    "native": "ಕನ್ನಡ",      "image": "https://images.unsplash.com/photo-1583032015879-e50d332945b1?w=400&q=80"},
    {"code": "pa", "name": "Punjabi",    "native": "ਪੰਜਾਬੀ",     "image": "https://images.unsplash.com/photo-1514222139-b57675ee3edb?w=400&q=80"},
    {"code": "bn", "name": "Bengali",    "native": "বাংলা",      "image": "https://images.unsplash.com/photo-1596402184320-417d7178b2cd?w=400&q=80"},
    {"code": "mr", "name": "Marathi",    "native": "मराठी",     "image": "https://images.unsplash.com/photo-1566552881560-0be862a7c445?w=400&q=80"},
    {"code": "gu", "name": "Gujarati",   "native": "ગુજરાતી",    "image": "https://images.unsplash.com/photo-1609947017136-9dab4f396541?w=400&q=80"},
    {"code": "or", "name": "Odia",       "native": "ଓଡ଼ିଆ",      "image": "https://images.unsplash.com/photo-1590080875515-8a3a8dc5735e?w=400&q=80"},
    {"code": "as", "name": "Assamese",   "native": "অসমীয়া",    "image": "https://images.unsplash.com/photo-1567157577867-05ccb1388e13?w=400&q=80"},
    {"code": "ur", "name": "Urdu",       "native": "اردو",      "image": "https://images.unsplash.com/photo-1585129777188-94600bc7b4b3?w=400&q=80"},
    {"code": "bh", "name": "Bhojpuri",   "native": "भोजपुरी",   "image": "https://images.unsplash.com/photo-1524492412937-b28074a5d7da?w=400&q=80"},
    {"code": "ra", "name": "Rajasthani", "native": "राजस्थानी",  "image": "https://images.unsplash.com/photo-1477587458883-47145ed94245?w=400&q=80"},
    {"code": "ha", "name": "Haryanvi",   "native": "हरियाणवी",  "image": "https://images.unsplash.com/photo-1558618666-fcd25c85f82e?w=400&q=80"},
    {"code": "ko", "name": "Konkani",    "native": "कोंकणी",    "image": "https://images.unsplash.com/photo-1512100356356-de1b84283e18?w=400&q=80"},
    {"code": "ma", "name": "Maithili",   "native": "मैथिली",    "image": "https://images.unsplash.com/photo-1548013146-72479768bada?w=400&q=80"},
    {"code": "sa", "name": "Santali",    "native": "ᱥᱟᱱᱛᱟᱲᱤ",    "image": "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=400&q=80"},
    {"code": "do", "name": "Dogri",      "native": "डोगरी",     "image": "https://images.unsplash.com/photo-1564507592333-c60657eea523?w=400&q=80"},
    {"code": "ks", "name": "Kashmiri",   "native": "کٲشُر",     "image": "https://images.unsplash.com/photo-1567696911980-2eed69a46042?w=400&q=80"},
    {"code": "sd", "name": "Sindhi",     "native": "سنڌي",      "image": "https://images.unsplash.com/photo-1587474260584-136574528ed5?w=400&q=80"},
    {"code": "tu", "name": "Tulu",       "native": "ತುಳು",       "image": "https://images.unsplash.com/photo-1580581096469-8afb14cd81f2?w=400&q=80"},
    {"code": "mn", "name": "Manipuri",   "native": "মণিপুরী",   "image": "https://images.unsplash.com/photo-1544735716-392fe2489ffa?w=400&q=80"},
]


def _seed_languages_if_needed():
    """Seeds master language list into Firebase if not already present."""
    existing = db_ops.get("languages")
    if not existing:
        lang_data = {}
        for lang in MASTER_LANGUAGES:
            lang_data[lang["code"]] = lang
        db_ops.set_val("languages", lang_data)
        print("Seeded 24 languages into Firebase.")


# ─── Endpoints ────────────────────────────────────────────────────────────────

class LanguagesInput(BaseModel):
    languages: List[str]

class FollowArtistInput(BaseModel):
    artistId: str
    artistName: str


@router.get("/languages")
async def get_languages():
    """Returns the master list of supported languages.
    Serves from Firebase cache, seeds on first call."""
    cached = db_ops.get("languages")
    if not cached:
        _seed_languages_if_needed()
        cached = db_ops.get("languages")
    
    # Convert dict to sorted list
    if isinstance(cached, dict):
        languages = sorted(cached.values(), key=lambda x: x.get("name", ""))
    else:
        languages = MASTER_LANGUAGES
    
    return {"languages": languages}


@router.post("/onboarding/languages")
async def select_languages(data: LanguagesInput, user: dict = Depends(get_current_user)):
    """Saves the user's preferred music languages."""
    db_ops.set_user_languages(user["uid"], data.languages)
    return {"status": "success", "message": "Languages saved"}


@router.get("/onboarding/artists")
async def get_onboarding_artists(
    user: dict = Depends(get_current_user),
    x_quality: str = Header("medium")
):
    """Fetches artists based on the user's selected languages.
    Results are cached in Firebase per language for instant loading."""
    languages = db_ops.get_user_languages(user["uid"])
    
    if not languages:
        raise HTTPException(status_code=400, detail="Please select languages first")
    
    all_artists = []
    
    for lang in languages:
        # Check Firebase cache first
        lang_key = lang.lower().strip()
        cached_artists = db_ops.get(f"artists_cache/{lang_key}")
        
        if cached_artists and isinstance(cached_artists, list):
            all_artists.extend(cached_artists)
        else:
            # Fetch from Saavn API and cache
            fetched = get_top_artists_by_language([lang], limit=8, quality=x_quality)
            if fetched:
                db_ops.set_val(f"artists_cache/{lang_key}", fetched)
                all_artists.extend(fetched)
    
    # Deduplicate by artist ID
    seen = set()
    unique_artists = []
    for a in all_artists:
        aid = a.get("id", "")
        if aid and aid not in seen:
            seen.add(aid)
            unique_artists.append(a)
    
    return {"artists": unique_artists}


@router.post("/onboarding/follow")
async def follow_artist(data: FollowArtistInput, user: dict = Depends(get_current_user)):
    """Follows an artist during or after onboarding."""
    db_ops.follow_artist(user["uid"], data.artistId, data.artistName)
    return {"status": "success", "message": f"Followed {data.artistName}"}
