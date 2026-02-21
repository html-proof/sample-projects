import time
from threading import Thread

def start_trending_scheduler():
    """Starts a background thread to recompute trending songs periodically."""
    def run_scheduler():
        while True:
            print("Refreshing trending songs...")
            # Logic to recompute trending from db_ops would go here
            time.sleep(1800) # Every 30 minutes
            
    thread = Thread(target=run_scheduler, daemon=True)
    thread.start()
