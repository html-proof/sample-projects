import urllib.request
import json
import urllib.parse

query = urllib.parse.quote("chotta mumabi malayalam song")
url = f"https://sample-projects-production.up.railway.app/api/search/songs?query={query}&page=1&limit=20"

try:
    req = urllib.request.Request(url, headers={'x-quality': 'medium'})
    res = urllib.request.urlopen(req)
    data = json.loads(res.read())
    
    with open('search_result.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Success")
except Exception as e:
    print(f"Error: {e}")
