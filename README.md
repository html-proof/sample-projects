# 🎵 Music Streaming Backend

A production-grade Spotify-like recommendation backend powered by the **JioSaavn API**, built with **FastAPI** and **Firebase Realtime Database**, deployed on **Railway**.

---

## Architecture

```
Mobile / Web App
      │
      │ HTTPS
      ▼
Railway (FastAPI backend)
      │
      ├── Firebase Auth       ← token verification
      ├── Firebase Realtime DB ← user data, cache, trending
      └── JioSaavn API        ← music data source
```

---

## Features

| Feature | Description |
|---|---|
| 🔍 Smart Search | Cached search across songs, artists, albums, playlists |
| 🎯 Recommendations | Personalized via listening history, likes, skips |
| 📈 Trending | Auto-computed every 30 min via background scheduler |
| 🔀 Smart Queue | Avoids repeated artists, skipped songs |
| 📅 Daily Mix | Generated from your top artists and recent plays |
| ⚡ Caching | Firebase-backed with per-type TTLs |
| 📱 Mobile-first | Slim responses, gzip, pagination |

---

## Quick Start

### 1. Clone & install

```bash
git clone <your-repo>
cd backend
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in FIREBASE_CREDENTIALS and FIREBASE_DATABASE_URL
```

### 3. Run locally

```bash
# Skip auth for local dev
BYPASS_AUTH=true uvicorn app:app --reload
```

API docs at: http://localhost:8000/docs

---

## Deploy to Railway

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and init
railway login
railway init

# Set environment variables
railway variables set FIREBASE_CREDENTIALS='{"type":"service_account",...}'
railway variables set FIREBASE_DATABASE_URL='https://your-db.firebaseio.com'

# Deploy
railway up
```

---

## API Reference

### Search

| Endpoint | Description |
|---|---|
| `GET /api/search?q=arijit` | Search everything |
| `GET /api/search/songs?q=tum hi ho` | Search songs |
| `GET /api/search/artists?q=ar rahman` | Search artists |
| `GET /api/search/albums?q=rockstar` | Search albums |
| `GET /api/search/playlists?q=chill` | Search playlists |

### Songs & Artists

| Endpoint | Description |
|---|---|
| `GET /api/songs/{id}` | Song details |
| `GET /api/songs/{id}/related` | Related songs |
| `GET /api/artists/{id}` | Artist profile |
| `GET /api/artists/{id}/songs` | Artist's songs |
| `GET /api/artists/{id}/albums` | Artist's albums |
| `GET /api/albums?id=...` | Album details |
| `GET /api/playlists?id=...` | Playlist details |

### User Events (require Auth header)

```
POST /api/play    { "songId": "...", "duration": 180, "completed": true }
POST /api/skip    { "songId": "..." }
POST /api/like    { "songId": "..." }
```

### Recommendations (require Auth header)

| Endpoint | Description |
|---|---|
| `GET /api/recommendations` | Personalized + trending |
| `GET /api/recommendations?currentSong=id` | Context-aware recs |
| `GET /api/queue/smart?seedSong=id` | Smart shuffle queue |
| `GET /api/mix/daily` | Daily mix playlist |
| `GET /api/trending` | Global trending songs |

---

## Firebase Database Schema

```
root
├── users/{userId}
│     ├── createdAt
│     ├── favoriteArtists[]
│     └── favoriteGenres[]
│
├── history/{userId}/played/{songId}/{pushId}
│     ├── timestamp
│     ├── duration
│     └── completed
│
├── likes/{userId}/{songId}           true
├── skipped/{userId}/{songId}         { timestamp }
├── current_playing/{userId}          { songId, startedAt }
├── search_history/{userId}/{pushId}  { query, timestamp }
│
├── song_stats/{songId}
│     ├── plays
│     ├── skips
│     └── likes
│
├── trending/daily                    { songs[], updatedAt }
│
└── cache
    ├── search_cache/{query}          { results, timestamp }
    ├── songs_cache/{songId}          { results, timestamp }
    ├── artists_cache/{artistId}      { results, timestamp }
    ├── albums_cache/{albumId}        { results, timestamp }
    └── playlist_cache/{playlistId}   { results, timestamp }
```

---

## Cache TTLs

| Collection | TTL |
|---|---|
| Songs | 24 hours |
| Artists | 7 days |
| Albums | 24 hours |
| Playlists | 24 hours |
| Search | 1 hour |
| Trending | 30 minutes |

---

## Recommendation Signals

The engine analyzes:
- ✅ **Liked songs** — strong positive boost
- ⏭️ **Skipped songs** — filtered out entirely
- 🔁 **Repeat listens** — increases artist weight
- 🎨 **Favorite artists** — detected from history
- 📍 **Current song** — seeds content-based filtering
- ⏰ **Time of day** — contextual label (morning/night)
- 📊 **Song stats** — completion rate, engagement score
- 🔥 **Trending** — popularity-weighted fallback

---

## Project Structure

```
backend/
├── app.py                  # FastAPI entry point
├── requirements.txt
├── Dockerfile
├── railway.json
├── .env.example
│
├── routes/
│   ├── search.py
│   ├── songs.py
│   ├── artists.py
│   ├── albums.py
│   ├── playlists.py
│   ├── events.py           # play / skip / like
│   └── recommendations.py
│
├── services/
│   ├── saavn.py            # JioSaavn API client
│   └── trending.py         # Scheduled trending recompute
│
├── recommender/
│   └── engine.py           # Full recommendation engine
│
├── firebase/
│   ├── client.py           # Firebase init + auth
│   └── db_ops.py           # All DB read/write helpers
│
├── cache/
│   └── store.py            # Cache layer with TTL
│
└── middleware/
    ├── auth.py             # Firebase token verification
    └── rate_limit.py       # 100 req/min per IP
```
