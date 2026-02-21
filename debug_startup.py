import uvicorn
import traceback
import sys

if __name__ == "__main__":
    try:
        uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
