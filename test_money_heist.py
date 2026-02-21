import os, sys, json
os.chdir('d:/new sample')
sys.path.append(os.getcwd())

from firebase.client import init_firebase
from services.saavn import search_songs, slim_song

init_firebase()

# Test 1: Fresh search
print("=== Test: 'money heist' ===")
res = search_songs('money heist', page=1, limit=5)
data = res.get('data', {})
results = data.get('results', [])
slimmed = [slim_song(s) for s in results[:5]]

print(f"Source: {res.get('source', 'api')}")
print(f"Total: {len(results)}")
for i, s in enumerate(slimmed):
    print(f"  {i+1}. {s['title']} - {s['artist']}")
    print(f"     Stream: {s['streamUrl'][:80]}...")

# Test 2: Cache hit
print("\n=== Cache hit test ===")
res2 = search_songs('money heist', page=1, limit=5)
print(f"Source: {res2.get('source', 'api')}")
