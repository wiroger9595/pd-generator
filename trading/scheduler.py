import time
import schedule  
import os
from config import SCHEDULE_CONFIG
from src.services.scanner_service import run_scan
from src.utils.logger import logger

def start_scheduler():
    """啟動排程任務"""
    tw_time = SCHEDULE_CONFIG.get("TW_RUN_TIME", "14:30")
    us_time = SCHEDULE_CONFIG.get("US_RUN_TIME", "06:00")

    logger.info(f"🚀 Trading System Scheduler Started (PID: {os.getpid()})")
    logger.info(f"📅 排程設定已載入:")
    logger.info(f"   - 台股 (TW): 每天 {tw_time} 執行")
    logger.info(f"   - 美股 (US): 每天 {us_time} 執行")

    schedule.every().day.at(tw_time).do(run_scan, "tw")
    schedule.every().day.at(us_time).do(run_scan, "us")

    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 排程服務停止")
            break
        except Exception as e:
            logger.error(f"❌ 排程發生未預期錯誤: {e}")
            time.sleep(60)

if __name__ == "__main__":
    start_scheduler()
