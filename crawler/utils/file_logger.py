# crawler/utils/file_logger.py
import os
import datetime

# Log directory: root/data/
LOG_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')

def log_results_to_file(results):
    """
    Appends a list of results to a daily log file.
    Example: data/crawler_results_2024-01-18.log
    """
    if not results:
        print("   ⚠️ No new data collected to write to log.", flush=True)
        return

    os.makedirs(LOG_DIR, exist_ok=True)
    
    # Get current date for filename
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    
    # Dynamic filename: crawler_results_2024-01-18.log
    filename = f"crawler_results_{date_str}.log"
    log_path = os.path.join(LOG_DIR, filename)
    
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- Batch Logged at {timestamp} ---\n")
            for item in results:
                line = (
                    f"[{item.get('platform', 'Unknown')}] "
                    f"[{item.get('keyword', 'No Keyword')}] "
                    f"{item.get('title', 'No Title')} "
                    f"({item.get('url', 'No URL')})\n"
                )
                f.write(line)
        print(f"📄 [File Log] Appended {len(results)} items to {log_path}", flush=True)
    except Exception as e:
        print(f"⚠️ Failed to write to log file: {e}", flush=True)
