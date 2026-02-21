import os, sys, json
os.chdir('d:/new sample')
sys.path.append(os.getcwd())

from firebase.client import init_firebase
from services.saavn import search_songs, slim_song, get_album, slim_album

init_firebase()

print("=== Album Recommendation Test ===")
res = search_songs('believer imagine dragons', page=1, limit=3)
data = res.get('data', {}).get('results', [])
slimmed = [slim_song(s) for s in data[:1]]

if slimmed:
    aid = slimmed[0].get('albumId', '')
    print("Top Song:", slimmed[0].get('title', ''))
    print("Album ID:", aid)
    print("Album Name:", slimmed[0].get('album', ''))
    
    if aid:
        a = get_album(aid)
        ad = a.get('data', {})
        songs = ad.get('songs', [])
        print("\nFull Album:", ad.get('name', ''))
        print("Total Tracks:", len(songs))
        for i, s in enumerate(songs):
            t = slim_song(s)
            print("  {}. {} ({})".format(i+1, t['title'], t['duration']))
    else:
        print("No album ID found")
else:
    print("No results")
