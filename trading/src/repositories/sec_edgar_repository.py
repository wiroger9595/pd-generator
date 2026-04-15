"""
SEC EDGAR Repository — 美股重大事件監控
來源 1：SEC EDGAR Atom Feed — 8-K (重大事件)、10-Q/10-K (財報)
來源 2：Google News RSS — 公司突發新聞（已有）
"""
import hashlib
import requests
from datetime import datetime, timedelta
from src.utils.logger import logger

# SEC EDGAR 最新申報 Atom feed（免費，無需 API key）
_EDGAR_ATOM = (
    "https://efts.sec.gov/LATEST/search-index?forms={forms}"
    "&dateRange=custom&startdt={start}&enddt={end}"
    "&hits.hits._source=period_of_report,file_date,entity_name,ticker,form_type"
    "&hits.hits.total=true"
)
_EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"


def _event_id(source: str, ticker: str, title: str, date: str) -> str:
    raw = f"{source}:{ticker}:{title}:{date}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def fetch_sec_filings(
    tickers: list[str],
    forms: str = "8-K",
    days_back: int = 1,
) -> list[dict]:
    """
    抓取指定公司的 SEC 申報
    forms: 逗號分隔，如 "8-K" 或 "8-K,6-K"
    8-K  = 重大事件（盈利警告、收購、CEO 異動等）
    10-Q = 季報
    10-K = 年報
    """
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    end   = datetime.now().strftime("%Y-%m-%d")

    results = []
    for ticker in tickers:
        try:
            resp = requests.get(
                _EDGAR_SEARCH,
                params={
                    "q": f'"{ticker}"',
                    "forms": forms,
                    "dateRange": "custom",
                    "startdt": start,
                    "enddt": end,
                },
                headers={"User-Agent": "trading-monitor bot@example.com"},
                timeout=20,
            )
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])
            for hit in hits[:10]:
                src = hit.get("_source", {})
                entity = src.get("entity_name", ticker)
                form   = src.get("form_type", forms)
                date_str = src.get("file_date", end)
                title = f"[{form}] {entity}"
                eid = _event_id("SEC", ticker, title, date_str)
                results.append({
                    "event_id": eid,
                    "source":   "SEC EDGAR",
                    "ticker":   ticker,
                    "title":    title,
                    "content":  f"{form} filing by {entity} on {date_str}",
                    "date":     date_str,
                    "form_type": form,
                })
        except Exception as e:
            logger.warning(f"[SEC EDGAR] {ticker} 失敗: {e}")

    # 若 tickers 為空，抓全市場 8-K 並比對 holdings
    if not tickers:
        results = _fetch_global_8k(forms, start, end)

    logger.info(f"[SEC EDGAR] 共 {len(results)} 筆申報")
    return results


def _fetch_global_8k(forms: str, start: str, end: str) -> list[dict]:
    """無指定 ticker 時：抓全市場最新 8-K（用於廣播模式）"""
    try:
        resp = requests.get(
            _EDGAR_SEARCH,
            params={
                "forms": forms,
                "dateRange": "custom",
                "startdt": start,
                "enddt": end,
                "hits.hits.total": "true",
            },
            headers={"User-Agent": "trading-monitor bot@example.com"},
            timeout=20,
        )
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        results = []
        for hit in hits[:30]:
            src = hit.get("_source", {})
            entity   = src.get("entity_name", "")
            ticker   = src.get("ticker", "")
            form     = src.get("form_type", forms)
            date_str = src.get("file_date", end)
            title = f"[{form}] {entity}"
            eid = _event_id("SEC", ticker, title, date_str)
            results.append({
                "event_id": eid,
                "source":   "SEC EDGAR",
                "ticker":   ticker,
                "title":    title,
                "content":  f"{form} filing by {entity} on {date_str}",
                "date":     date_str,
                "form_type": form,
            })
        return results
    except Exception as e:
        logger.warning(f"[SEC EDGAR] global fetch 失敗: {e}")
        return []
