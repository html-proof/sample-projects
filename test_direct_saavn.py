import os, sys
os.chdir('d:/new sample')
sys.path.append(os.getcwd())

from firebase.client import init_firebase
init_firebase()

from services.saavn import _search_jiosaavn_direct

print("=== Test 1: English Song ===")
r1 = _search_jiosaavn_direct("Believer Imagine Dragons", limit=2)
for s in r1:
    has_stream = "YES" if s['streamUrl'] else "NO"
    print(f"  {s['name']} | Artist: {s['artist']} | Stream: {has_stream}")
    if s['streamUrl']:
        print(f"    URL: {s['streamUrl'][:80]}")

print("\n=== Test 2: Hindi Song ===")
r2 = _search_jiosaavn_direct("Tum Hi Ho", limit=2)
for s in r2:
    has_stream = "YES" if s['streamUrl'] else "NO"
    print(f"  {s['name']} | Stream: {has_stream}")
    if s['streamUrl']:
        print(f"    URL: {s['streamUrl'][:80]}")

print("\n=== Test 3: Rare Song ===")
r3 = _search_jiosaavn_direct("Bella Ciao Money Heist", limit=2)
for s in r3:
    has_stream = "YES" if s['streamUrl'] else "NO"
    print(f"  {s['name']} | Stream: {has_stream}")
