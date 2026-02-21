import requests
import sys

BASE_URL = "http://localhost:8000/api"

def test_song_refresh(song_id="3IoDK8qI"):
    print(f"Testing song refresh for ID: {song_id}")
    
    # 1. Normal fetch
    print("Step 1: Normal fetch (cached or fresh)...")
    res1 = requests.get(f"{BASE_URL}/songs/{song_id}")
    if res1.status_code != 200:
        print(f"FAILED: Initial fetch returned {res1.status_code}")
        return
    
    data1 = res1.json()
    url1 = data1.get("streamUrl")
    print(f"URL 1: {url1[:50]}...")
    
    # 2. Forced refresh
    print("\nStep 2: Forced refresh...")
    res2 = requests.get(f"{BASE_URL}/songs/{song_id}?refresh=true")
    if res2.status_code != 200:
        print(f"FAILED: Refresh fetch returned {res2.status_code}")
        return
        
    data2 = res2.json()
    url2 = data2.get("streamUrl")
    print(f"URL 2: {url2[:50]}...")
    
    # 3. Verify reachability of the new URL
    print("\nStep 3: Verifying URL reachability...")
    if url2:
        try:
            head_res = requests.head(url2, timeout=5)
            print(f"HEAD request status: {head_res.status_code}")
            if head_res.status_code in (200, 206):
                print("SUCCESS: URL is reachable and valid for streaming.")
            else:
                print(f"WARNING: URL returned unexpected status {head_res.status_code}")
        except Exception as e:
            print(f"FAILED: URL reachability check failed: {e}")
    else:
        print("FAILED: No stream URL returned.")

if __name__ == "__main__":
    test_song_refresh()
