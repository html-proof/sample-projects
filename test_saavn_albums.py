import urllib.request
import json
import urllib.parse

query = urllib.parse.quote("mumbai")
url = f"https://saavn.sumit.co/api/search/albums?query={query}"

try:
    req = urllib.request.Request(url, headers={'Accept': 'application/json'})
    res = urllib.request.urlopen(req)
    data = json.loads(res.read())
    
    with open('saavn_album_search.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Success album search")
except Exception as e:
    print(f"Error: {e}")
