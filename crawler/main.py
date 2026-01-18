# crawler/main.py
import sys
import os
from .core.scheduler import start_scheduler, job
from .config import CRAWLER_INTERVAL_MINUTES

def run_crawler_service():
    # Check for manual run flag
    if "--once" in sys.argv:
        print("🚀 Manual Trigger: Running crawler once...")
        job()
        print("✅ Manual Run Completed.")
        return

    # Start Scheduler
    try:
        # Run every X minutes (from config)
        start_scheduler(interval_minutes=CRAWLER_INTERVAL_MINUTES)
    except KeyboardInterrupt:
        print("\n🛑 Crawler Service Stopped.")

if __name__ == "__main__":
    run_crawler_service()