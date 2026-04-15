"""
TWSE MOPS 重大訊息 Repository
來源 1：公開資訊觀測站 (MOPS) — 台灣上市公司重大訊息
來源 2：FinMind TaiwanStockNews — 財經新聞（已延伸）
"""
import hashlib
import requests
from datetime import datetime, timedelta
from src.utils.logger import logger

_MOPS_URL = "https://mops.twse.com.tw/mops/web/ajax_t05sr01"
_FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


def _event_id(source: str, ticker: str, title: str, date: str) -> str:
    """生成唯一事件 ID（SHA256 前 16 字元）"""
    raw = f"{source}:{ticker}:{title}:{date}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── MOPS 重大訊息 ─────────────────────────────────────────────────────────


def fetch_mops_announcements(tickers: list[str], days_back: int = 1) -> list[dict]:
    """
    抓取 MOPS 上市公司重大訊息
    回傳 [{"event_id","source","ticker","title","content","date"}, ...]
    """
    today = datetime.now()
    start = (today - timedelta(days=days_back)).strftime("%Y%m%d")
    end   = today.strftime("%Y%m%d")

    results = []
    for ticker in tickers:
        try:
            resp = requests.post(
                _MOPS_URL,
                data={
                    "step": "1",
                    "kind": "A",
                    "co_id": ticker,
                    "b_date": start,
                    "e_date": end,
                    "TYPEK": "sii",
                },
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://mops.twse.com.tw/"},
                timeout=15,
            )
            if resp.status_code != 200:
                continue

            # 解析 HTML 表格
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table", class_="hasBorder")
            if not table:
                continue

            for tr in table.find_all("tr")[1:]:
                tds = tr.find_all("td")
                if len(tds) < 3:
                    continue
                date_str = tds[0].get_text(strip=True)
                title    = tds[1].get_text(strip=True)
                content  = tds[2].get_text(strip=True) if len(tds) > 2 else ""
                eid = _event_id("MOPS", ticker, title, date_str)
                results.append({
                    "event_id": eid,
                    "source":   "MOPS",
                    "ticker":   ticker,
                    "title":    title,
                    "content":  content[:200],
                    "date":     date_str,
                })
        except Exception as e:
            logger.warning(f"[MOPS] {ticker} 抓取失敗: {e}")

    logger.info(f"[MOPS] 抓取完成，共 {len(results)} 則重大訊息")
    return results


# ── FinMind 台股新聞 ──────────────────────────────────────────────────────


def fetch_finmind_news(tickers: list[str], api_token: str, days_back: int = 1) -> list[dict]:
    """
    使用 FinMind TaiwanStockNews 抓取財經新聞
    """
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    results = []

    for ticker in tickers:
        try:
            resp = requests.get(
                _FINMIND_URL,
                params={
                    "dataset": "TaiwanStockNews",
                    "data_id": ticker,
                    "start_date": start,
                    "token": api_token,
                },
                timeout=15,
            )
            data = resp.json()
            if data.get("status") != 200:
                continue
            for item in data.get("data", []):
                title   = item.get("title", "")
                date_str = item.get("date", "")[:10]
                eid = _event_id("FinMind", ticker, title, date_str)
                results.append({
                    "event_id": eid,
                    "source":   "FinMind",
                    "ticker":   ticker,
                    "title":    title,
                    "content":  item.get("description", "")[:200],
                    "date":     date_str,
                })
        except Exception as e:
            logger.warning(f"[FinMind News] {ticker} 失敗: {e}")

    logger.info(f"[FinMind News] 抓取完成，共 {len(results)} 則新聞")
    return results
