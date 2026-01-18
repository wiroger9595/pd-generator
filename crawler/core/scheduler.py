# crawler/core/scheduler.py
import time
import schedule
import random
from ..config import KEYWORDS, SOCIAL_PLATFORMS, RSSHUB_BASE_URL, FB_PRIVATE_GROUPS
from ..services.google import fetch_google_data
from ..services.rss import fetch_rss_data
from ..services.facebook_private import fetch_private_group_posts
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
        
    time.sleep(2)

    # 3. Facebook Private Groups
    if FB_PRIVATE_GROUPS:
        print(f"\n👥 [Facebook] Processing {len(FB_PRIVATE_GROUPS)} private groups...")
        for group_id in FB_PRIVATE_GROUPS:
            try:
                fb_results = fetch_private_group_posts(group_id, pages=2)
                log_results_to_file(fb_results)
                # Polite sleep between groups only if there are multiple
                if len(FB_PRIVATE_GROUPS) > 1:
                    time.sleep(random.uniform(5, 10))
            except Exception as e:
                print(f"❌ Error scraping group {group_id}: {e}")

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
