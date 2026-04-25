"""
多維度共振彙整服務
買進：技術面、基本面、籌碼面、消息面 同時掃描，找出多維共振股票
賣出：基本面、籌碼面、消息面 掃描庫存+觀察名單，找出多維警示股票
      (技術面賣出訊號由各自的 daily-analysis/sell 獨立發出)
"""
import asyncio
from src.utils.logger import logger
from src.utils.ticker import normalize_ticker

DIMENSION_LABELS = {
    "technical": "技術面",
    "fundamental": "基本面",
    "chip": "籌碼面",
    "news": "消息面",
}


_normalize_ticker = normalize_ticker  # 共用 utils/ticker.py


def _merge_dimension(merged: dict, items: list, dim_key: str):
    """將單一面向的推薦清單合併進 merged dict"""
    label = DIMENSION_LABELS.get(dim_key, dim_key)
    for item in items:
        ticker = item.get("ticker", "")
        norm = _normalize_ticker(ticker)
        if not norm:
            continue
        if norm not in merged:
            merged[norm] = {
                "ticker": ticker,           # 保留原始 ticker（含 .TW 後綴）
                "name": item.get("name", ticker),
                "dimensions": {},
                "total_score": 0,
            }
        else:
            # 若有 .TW 後綴版本，優先保留
            if ".TW" in ticker or ".TWO" in ticker:
                merged[norm]["ticker"] = ticker

        score = item.get("score", 0)
        reason = item.get("reason", "")
        merged[norm]["dimensions"][label] = {"score": score, "reason": reason}
        merged[norm]["total_score"] += score


async def _safe_call(coro, label: str, key: str = "recommendations") -> list:
    """安全呼叫各面向，發生錯誤時回傳空清單。
    key: 買進用 'recommendations'，賣出用 'sell_signals'
    """
    try:
        result = await coro
        if result.get("status") != "success":
            logger.warning(f"[Summary] {label} returned non-success: {result.get('error', '')}")
            return []
        return result.get(key, [])
    except Exception as e:
        logger.warning(f"[Summary] {label} failed: {e}")
        return []


# ─────────────────────────────────────────────
# 台股四維共振
# ─────────────────────────────────────────────

async def get_tw_summary_buy(top_n: int = 5, min_dimensions: int = 2) -> dict:
    """
    台股多維度共振買進彙整
    min_dimensions: 至少幾個面向同時看多才納入
    """
    from src.services.recommendation_service import get_tw_recommendations
    from src.services.fundamental_service import get_tw_fundamental_buy
    from src.services.chip_service import get_tw_chip_buy
    from src.services.news_service import get_tw_news_buy

    logger.info("[Summary] 開始台股四維掃描...")

    tech_items, fund_items, chip_items, news_items = await asyncio.gather(
        _safe_call(get_tw_recommendations(top_n=50, max_scan=50), "技術面"),
        _safe_call(get_tw_fundamental_buy(top_n=50, max_scan=50), "基本面"),
        _safe_call(get_tw_chip_buy(top_n=50, max_scan=50), "籌碼面"),
        _safe_call(get_tw_news_buy(top_n=50, max_scan=50), "消息面"),
    )

    merged: dict = {}
    _merge_dimension(merged, tech_items, "technical")
    _merge_dimension(merged, fund_items, "fundamental")
    _merge_dimension(merged, chip_items, "chip")
    _merge_dimension(merged, news_items, "news")

    # 過濾：至少 min_dimensions 個面向
    resonant = [
        v for v in merged.values()
        if len(v["dimensions"]) >= min_dimensions
    ]

    # 排序：面向數多 > 總分高
    resonant.sort(key=lambda x: (len(x["dimensions"]), x["total_score"]), reverse=True)
    top = resonant[:top_n]

    logger.info(f"[Summary] 台股掃描完成，共振 {len(resonant)} 檔，取前 {len(top)} 檔")
    return {
        "status": "success",
        "market": "TW",
        "scanned_tickers": len(merged),
        "resonant_count": len(resonant),
        "min_dimensions": min_dimensions,
        "results": top,
    }


# ─────────────────────────────────────────────
# 美股四維共振
# ─────────────────────────────────────────────

async def get_us_summary_buy(top_n: int = 5, min_dimensions: int = 2) -> dict:
    """
    美股多維度共振買進彙整
    技術面合併 Polygon + AlphaVantage + Tiingo 三個 provider 的最高分
    """
    from src.services.recommendation_service import get_provider_recommendations
    from src.services.fundamental_service import get_us_fundamental_buy
    from src.services.chip_service import get_us_chip_buy
    from src.services.news_service import get_us_news_buy

    logger.info("[Summary] 開始美股四維掃描...")

    # 技術面：三個 provider 並行，取最高分
    poly_items, av_items, tiingo_items, fund_items, chip_items, news_items = await asyncio.gather(
        _safe_call(get_provider_recommendations("polygon", top_n=30, max_scan=30), "技術面(Polygon)"),
        _safe_call(get_provider_recommendations("alpha_vantage", top_n=30, max_scan=30), "技術面(AV)"),
        _safe_call(get_provider_recommendations("tiingo", top_n=30, max_scan=30), "技術面(Tiingo)"),
        _safe_call(get_us_fundamental_buy(top_n=30, max_scan=30), "基本面"),
        _safe_call(get_us_chip_buy(top_n=30, max_scan=30), "籌碼面"),
        _safe_call(get_us_news_buy(top_n=30, max_scan=30), "消息面"),
    )

    # 合併三個技術面 provider，同一 ticker 取最高分
    tech_merged: dict = {}
    for provider_label, items in [("Polygon", poly_items), ("AV", av_items), ("Tiingo", tiingo_items)]:
        for item in items:
            t = _normalize_ticker(item.get("ticker", ""))
            if not t:
                continue
            existing = tech_merged.get(t)
            if existing is None or item.get("score", 0) > existing.get("score", 0):
                providers = tech_merged.get(t, {}).get("providers", [])
                providers.append(provider_label)
                tech_merged[t] = {**item, "providers": providers}
            else:
                tech_merged[t]["providers"].append(provider_label)
                # Append reason
                new_reason = item.get("reason", "")
                if new_reason and new_reason not in tech_merged[t].get("reason", ""):
                    tech_merged[t]["reason"] = tech_merged[t].get("reason", "") + f" | {new_reason}"
    tech_items = list(tech_merged.values())

    merged: dict = {}
    _merge_dimension(merged, tech_items, "technical")
    _merge_dimension(merged, fund_items, "fundamental")
    _merge_dimension(merged, chip_items, "chip")
    _merge_dimension(merged, news_items, "news")

    resonant = [
        v for v in merged.values()
        if len(v["dimensions"]) >= min_dimensions
    ]
    resonant.sort(key=lambda x: (len(x["dimensions"]), x["total_score"]), reverse=True)
    top = resonant[:top_n]

    logger.info(f"[Summary] 美股掃描完成，共振 {len(resonant)} 檔，取前 {len(top)} 檔")
    return {
        "status": "success",
        "market": "US",
        "scanned_tickers": len(merged),
        "resonant_count": len(resonant),
        "min_dimensions": min_dimensions,
        "results": top,
    }


# ─────────────────────────────────────────────
# 台股四維警示（賣出）
# ─────────────────────────────────────────────

async def get_tw_summary_sell(min_dimensions: int = 2) -> dict:
    """
    台股多維度共振賣出警示
    掃描庫存+觀察名單，基本面/籌碼面/消息面同時觸發賣出訊號的股票優先警示
    技術面賣出由 /api/daily-analysis/sell/tw 獨立處理
    """
    from src.services.fundamental_service import get_tw_fundamental_sell
    from src.services.chip_service import get_tw_chip_sell
    from src.services.news_service import get_tw_news_sell

    logger.info("[Summary] 開始台股賣出三維掃描...")

    fund_items, chip_items, news_items = await asyncio.gather(
        _safe_call(get_tw_fundamental_sell(), "基本面", key="sell_signals"),
        _safe_call(get_tw_chip_sell(), "籌碼面", key="sell_signals"),
        _safe_call(get_tw_news_sell(), "消息面", key="sell_signals"),
    )

    merged: dict = {}
    _merge_dimension(merged, fund_items, "fundamental")
    _merge_dimension(merged, chip_items, "chip")
    _merge_dimension(merged, news_items, "news")

    # 賣出：至少 min_dimensions 個面向都警示才納入
    alerts = [v for v in merged.values() if len(v["dimensions"]) >= min_dimensions]
    # 分數越負越危險，排在前面
    alerts.sort(key=lambda x: (len(x["dimensions"]), x["total_score"]))

    logger.info(f"[Summary] 台股賣出掃描完成，警示 {len(alerts)} 檔")
    return {
        "status": "success",
        "market": "TW",
        "type": "summary_sell",
        "scanned_tickers": len(merged),
        "alert_count": len(alerts),
        "min_dimensions": min_dimensions,
        "results": alerts,
    }


# ─────────────────────────────────────────────
# 美股四維警示（賣出）
# ─────────────────────────────────────────────

async def get_us_summary_sell(min_dimensions: int = 2) -> dict:
    """
    美股多維度共振賣出警示
    掃描庫存+觀察名單，基本面/籌碼面/消息面同時觸發賣出訊號的股票優先警示
    """
    from src.services.fundamental_service import get_us_fundamental_sell
    from src.services.chip_service import get_us_chip_sell
    from src.services.news_service import get_us_news_sell

    logger.info("[Summary] 開始美股賣出三維掃描...")

    fund_items, chip_items, news_items = await asyncio.gather(
        _safe_call(get_us_fundamental_sell(), "基本面", key="sell_signals"),
        _safe_call(get_us_chip_sell(), "籌碼面", key="sell_signals"),
        _safe_call(get_us_news_sell(), "消息面", key="sell_signals"),
    )

    merged: dict = {}
    _merge_dimension(merged, fund_items, "fundamental")
    _merge_dimension(merged, chip_items, "chip")
    _merge_dimension(merged, news_items, "news")

    alerts = [v for v in merged.values() if len(v["dimensions"]) >= min_dimensions]
    alerts.sort(key=lambda x: (len(x["dimensions"]), x["total_score"]))

    logger.info(f"[Summary] 美股賣出掃描完成，警示 {len(alerts)} 檔")
    return {
        "status": "success",
        "market": "US",
        "type": "summary_sell",
        "scanned_tickers": len(merged),
        "alert_count": len(alerts),
        "min_dimensions": min_dimensions,
        "results": alerts,
    }


# ─────────────────────────────────────────────
# 每日統整：買進 + 賣出 同時跑，合成一則 LINE
# ─────────────────────────────────────────────

async def get_tw_daily_summary(top_n: int = 5, min_dimensions: int = 2) -> dict:
    """台股每日統整：買進共振 + 賣出警示 同時掃描，回傳合併結果"""
    logger.info("[Summary] 台股每日統整開始...")
    buy_result, sell_result = await asyncio.gather(
        get_tw_summary_buy(top_n=top_n, min_dimensions=min_dimensions),
        get_tw_summary_sell(min_dimensions=min_dimensions),
    )
    return {
        "status": "success",
        "market": "TW",
        "buy": buy_result,
        "sell": sell_result,
    }


async def get_us_daily_summary(top_n: int = 5, min_dimensions: int = 2) -> dict:
    """美股每日統整：買進共振 + 賣出警示 同時掃描，回傳合併結果"""
    logger.info("[Summary] 美股每日統整開始...")
    buy_result, sell_result = await asyncio.gather(
        get_us_summary_buy(top_n=top_n, min_dimensions=min_dimensions),
        get_us_summary_sell(min_dimensions=min_dimensions),
    )
    return {
        "status": "success",
        "market": "US",
        "buy": buy_result,
        "sell": sell_result,
    }
