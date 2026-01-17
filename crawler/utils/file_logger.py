# crawler/utils/file_logger.py
import os
import datetime

# Log file path: root/data/crawler_results.log
LOG_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'crawler_results.log')

def log_results_to_file(results):
    """
    Appends a list of results to a log file in a human-readable format.
    """
    if not results:
        print("   ⚠️ No new data collected to write to log.")
        return

    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n--- Batch Logged at {timestamp} ---\n")
            for item in results:
                line = (
                    f"[{item.get('platform', 'Unknown')}] "
                    f"[{item.get('keyword', 'No Keyword')}] "
                    f"{item.get('title', 'No Title')} "
                    f"({item.get('url', 'No URL')})\n"
                )
                f.write(line)
        print(f"📄 [File Log] Appended {len(results)} items to {LOG_PATH}")
    except Exception as e:
        print(f"⚠️ Failed to write to log file: {e}")
