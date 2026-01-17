# crawler/main.py
import sys
import os
from .core.scheduler import start_scheduler

def run_crawler_service():
    # Start Scheduler
    try:
        start_scheduler(interval_minutes=10)
    except KeyboardInterrupt:
        print("\n🛑 Crawler Service Stopped.")

if __name__ == "__main__":
    run_crawler_service()