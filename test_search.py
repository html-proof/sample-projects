import json
from services.saavn import search_songs, slim_song

def main():
    query = "chotta mumabi malayalam song"
    print(f"Searching for: {query}")
    results = search_songs(query, 1, 10)
    
    if isinstance(results, dict) and "data" in results:
        data = results["data"]
        if isinstance(data, dict) and "results" in data:
            data["results"] = [slim_song(s, quality="medium") for s in data["results"]]
            
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
