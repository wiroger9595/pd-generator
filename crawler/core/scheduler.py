# crawler/core/scheduler.py
import time
import schedule
import random
from ..config import KEYWORDS, SOCIAL_PLATFORMS, RSSHUB_BASE_URL
from ..services.google import fetch_google_data
from ..services.rss import fetch_rss_data
from ..utils.file_logger import log_results_to_file

def job():
    print(f"\n=== 🚀 Starting Crawler Job: {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    
    # 1. Google Search
    try:
        google_results = fetch_google_data(KEYWORDS, SOCIAL_PLATFORMS)
        log_results_to_file(google_results)
    except Exception as e:
        print(f"❌ Error in Google job: {e}")

    # Random sleep between major tasks
    time.sleep(2)

    # 2. RSSHub
    try:
        rss_results = fetch_rss_data(KEYWORDS, RSSHUB_BASE_URL)
        log_results_to_file(rss_results)
    except Exception as e:
        print(f"❌ Error in RSS job: {e}")

    print("=== ✅ Job Completed, waiting for next schedule ===\n")

def start_scheduler(interval_minutes=10):
    print(f"🕷️ Crawler Service Initialized (Interval: {interval_minutes} min)")
    
    # Run once immediately
    job()
    
    # Schedule
    schedule.every(interval_minutes).minutes.do(job)
    
    while True:
        schedule.run_pending()
        time.sleep(1)
