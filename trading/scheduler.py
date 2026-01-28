import time
import schedule  
import os
import requests
from config import SCHEDULE_CONFIG
from src.utils.logger import logger

def trigger_scan_via_api(market):
    """透過 API 觸發掃描，讓主程式處理連線與交易"""
    try:
        url = f"http://127.0.0.1:8002/api/scan/full/{market}"
        res = requests.post(url, timeout=5)
        if res.status_code == 200:
            logger.info(f"📡 [排程] 已成功觸發 {market.upper()} 掃描 API")
        else:
            logger.error(f"❌ [排程] 觸發 {market.upper()} API 失敗: {res.status_code}")
    except Exception as e:
        logger.error(f"❌ [排程] 連線至 API 失敗: {e}")

def start_scheduler():
    """啟動排程任務"""
    tw_time = SCHEDULE_CONFIG.get("TW_RUN_TIME", "14:35")
    us_time = SCHEDULE_CONFIG.get("US_RUN_TIME", "06:15")
    crypto_time = SCHEDULE_CONFIG.get("CRYPTO_RUN_TIME", "00:00")

    logger.info(f"🚀 Trading System Scheduler Started (PID: {os.getpid()})")
    logger.info(f"📅 排程設定已載入:")
    logger.info(f"   - 台股 (TW): 每天 {tw_time}")
    logger.info(f"   - 美股 (US): 每天 {us_time}")
    logger.info(f"   - 區塊鏈 (Crypto): 每天 {crypto_time}")

    schedule.every().day.at(tw_time).do(trigger_scan_via_api, "tw")
    schedule.every().day.at(us_time).do(trigger_scan_via_api, "us")
    schedule.every().day.at(crypto_time).do(trigger_scan_via_api, "crypto")

    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 排程服務停止")
            break
        except Exception as e:
            logger.error(f"❌ 排程異常: {e}")
            time.sleep(60)

if __name__ == "__main__":
    start_scheduler()
