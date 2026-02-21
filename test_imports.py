import sys
import traceback

modules = [
    "routes.search",
    "routes.songs",
    "routes.artists",
    "routes.albums",
    "routes.playlists",
    "routes.events",
    "routes.recommendations",
    "routes.onboarding",
    "routes.home"
]

for mod_name in modules:
    print(f"Testing import of {mod_name}...")
    try:
        __import__(mod_name)
        print(f"SUCCESS: {mod_name} imported.")
    except Exception:
        print(f"FAILED: {mod_name} import error:")
        traceback.print_exc()
        # Don't exit, try others
    print("-" * 20)
