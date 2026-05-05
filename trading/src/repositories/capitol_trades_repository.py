"""
Capitol Trades Repository — 抓取 capitoltrades.com Next.js RSC 資料流
資料來源：國會議員 STOCK Act 申報（美股買賣）

技術說明：
  capitoltrades.com 是 Next.js App Router 應用，直接 GET HTML 只拿到骨架。
  改用 RSC（React Server Component）端點，加上 ?_rsc=1 參數，
  回傳 text/x-component 格式（RSC 行協議），其中含有未 escaped 的 data[] JSON。
"""
import re
import json
import requests
from src.utils.logger import logger

_BASE_URL = "https://www.capitoltrades.com"
_RSC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/x-component",
    "RSC": "1",
}
_DATA_KEY = '"data":['


def _clean_ticker(raw: str) -> str:
    """'MSFT:US' → 'MSFT'"""
    if not raw:
        return ""
    return raw.split(":")[0]


def _parse_rsc(text: str) -> list[dict]:
    """從 RSC 資料流中找到 data:[ 陣列並解析"""
    idx = text.find(_DATA_KEY)
    if idx < 0:
        logger.warning("[CongressTrades] RSC 回應中找不到 data[] 陣列")
        return []
    start = idx + len(_DATA_KEY) - 1  # 指向 [
    try:
        arr, _ = json.JSONDecoder().raw_decode(text, start)
        return arr
    except json.JSONDecodeError as e:
        logger.error(f"[CongressTrades] data[] 解析失敗: {e}")
        return []


def _normalize(raw: dict) -> dict:
    """將 capitoltrades 原始 dict 轉成統一格式"""
    pol = raw.get("politician") or {}
    issuer = raw.get("issuer") or {}
    ticker = _clean_ticker(issuer.get("issuerTicker", ""))
    return {
        "tx_id":          raw.get("_txId"),
        "politician_id":  raw.get("_politicianId"),
        "politician":     f"{pol.get('firstName', '')} {pol.get('lastName', '')}".strip(),
        "party":          pol.get("party", ""),
        "chamber":        raw.get("chamber", ""),
        "state":          pol.get("_stateId", "").upper(),
        "issuer_name":    issuer.get("issuerName", ""),
        "ticker":         ticker,
        "sector":         issuer.get("sector") or "",
        "tx_type":        raw.get("txType", ""),       # "buy" | "sell"
        "tx_date":        raw.get("txDate", ""),
        "pub_date":       raw.get("pubDate", ""),
        "reporting_gap":  raw.get("reportingGap"),
        "price":          raw.get("price"),
        "value":          raw.get("value"),
        "owner":          raw.get("owner", ""),
    }


def fetch_trades(pages: int = 3, page_size: int = 96, months: int = 0) -> list[dict]:
    """
    爬取最新幾頁的國會議員交易（透過 Next.js RSC 端點）。

    Args:
        pages:     最多爬幾頁（每頁 96 筆）；months > 0 時自動擴頁
        page_size: 每頁筆數（capitoltrades 支援 20 / 96）
        months:    若 > 0，爬取直到 tx_date < 今天往前 months 個月為止

    Returns:
        list[dict]: 正規化後的交易列表，已依 tx_date 降冪排序
    """
    from datetime import date, timedelta
    cutoff = ""
    if months > 0:
        cutoff = (date.today() - timedelta(days=months * 30)).isoformat()
        pages = max(pages, months * 4)   # 估算：每月約 4 頁

    all_trades: list[dict] = []
    seen_ids: set[int] = set()

    for page in range(1, pages + 1):
        try:
            resp = requests.get(
                f"{_BASE_URL}/trades",
                params={"pageSize": page_size, "page": page, "_rsc": "1"},
                headers=_RSC_HEADERS,
                timeout=20,
            )
            if resp.status_code != 200:
                logger.warning(f"[CongressTrades] HTTP {resp.status_code} page={page}")
                break
            raw_list = _parse_rsc(resp.text)
            if not raw_list:
                logger.info(f"[CongressTrades] page={page} 無資料，停止翻頁")
                break
            oldest_on_page = ""
            for raw in raw_list:
                tx_id = raw.get("_txId")
                if tx_id and tx_id not in seen_ids:
                    seen_ids.add(tx_id)
                    normalized = _normalize(raw)
                    all_trades.append(normalized)
                    d = normalized["tx_date"] or ""
                    if d and (not oldest_on_page or d < oldest_on_page):
                        oldest_on_page = d
            logger.info(f"[CongressTrades] page={page} 取得 {len(raw_list)} 筆，累計 {len(all_trades)}")
            # 已抓到 cutoff 日期之前就停
            if cutoff and oldest_on_page and oldest_on_page < cutoff:
                logger.info(f"[CongressTrades] 已達 {months} 個月截止日 {cutoff}，停止翻頁")
                break
        except Exception as e:
            logger.error(f"[CongressTrades] 爬取 page={page} 失敗: {e}")
            break

    # 過濾掉 cutoff 之前的資料
    if cutoff:
        all_trades = [t for t in all_trades if (t["tx_date"] or "") >= cutoff]

    all_trades.sort(key=lambda x: x["tx_date"] or "", reverse=True)
    return all_trades
