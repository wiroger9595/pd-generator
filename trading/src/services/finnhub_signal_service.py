"""
Finnhub 訊號分析 Service — 把目標價變動、評等變化、EPS surprise 轉成可加分的訊號
"""
import asyncio
from src.utils.logger import logger
from src.repositories.finnhub_repository import (
    get_price_target,
    get_recommendation_trends,
    get_upgrade_downgrade,
    get_earnings_surprises,
)


def _analyze_target(target: dict | None) -> tuple[int, str]:
    """目標價中位 vs 平均，分析師人數越多越可信"""
    if not target:
        return 0, ""
    median = target.get("targetMedian") or target.get("targetMean") or 0
    n = target.get("numberOfAnalysts") or 0
    if not median or not n:
        return 0, ""
    if n >= 20:
        return 10, f"目標價中位 {median} ({n} 位分析師)"
    if n >= 10:
        return 6, f"目標價中位 {median} ({n} 位分析師)"
    return 3, f"目標價中位 {median} ({n} 位分析師)"


def _analyze_recommendation_trend(trends: list[dict]) -> tuple[int, str]:
    """比對最新月 vs 上一月：strongBuy + buy 增加 → 加分"""
    if len(trends) < 2:
        return 0, ""
    latest, prev = trends[0], trends[1]
    bull_now  = (latest.get("strongBuy", 0) or 0) + (latest.get("buy", 0) or 0)
    bull_prev = (prev.get("strongBuy", 0)  or 0) + (prev.get("buy", 0)  or 0)
    delta = bull_now - bull_prev
    if delta >= 3:
        return 15, f"買進評等月增 {delta} 位"
    if delta >= 1:
        return 8, f"買進評等月增 {delta} 位"
    if delta <= -3:
        return -10, f"買進評等月減 {-delta} 位"
    return 0, ""


def _analyze_upgrades(events: list[dict], days: int = 30) -> tuple[int, str]:
    """近 N 天的 upgrade 數量"""
    if not events:
        return 0, ""
    import time
    cutoff = int(time.time()) - days * 86400
    ups = [e for e in events if e.get("action") == "up" and e.get("gradeTime", 0) >= cutoff]
    downs = [e for e in events if e.get("action") == "down" and e.get("gradeTime", 0) >= cutoff]
    score = len(ups) * 5 - len(downs) * 5
    score = max(-15, min(20, score))
    if not ups and not downs:
        return 0, ""
    return score, f"近 {days} 天 升級 {len(ups)} / 降級 {len(downs)}"


def _analyze_eps_surprise(surprises: list[dict]) -> tuple[int, str]:
    """最新一季 EPS surprise（實際 vs 預期）"""
    if not surprises:
        return 0, ""
    latest = surprises[0]
    pct = latest.get("surprisePercent")
    if pct is None:
        actual   = latest.get("actual") or 0
        estimate = latest.get("estimate") or 0
        if not estimate:
            return 0, ""
        pct = (actual - estimate) / abs(estimate) * 100
    if pct >= 20:
        return 25, f"EPS 超預期 {pct:.1f}%"
    if pct >= 10:
        return 15, f"EPS 超預期 {pct:.1f}%"
    if pct >= 5:
        return 8, f"EPS 超預期 {pct:.1f}%"
    if pct <= -10:
        return -15, f"EPS 不如預期 {pct:.1f}%"
    return 0, ""


async def analyze_finnhub_signals(ticker: str) -> dict:
    """
    並行抓 4 種訊號，整合成單一分數
    """
    ticker = ticker.upper()
    loop = asyncio.get_running_loop()

    target, trends, events, surprises = await asyncio.gather(
        loop.run_in_executor(None, get_price_target,           ticker),
        loop.run_in_executor(None, get_recommendation_trends,  ticker),
        loop.run_in_executor(None, get_upgrade_downgrade,      ticker),
        loop.run_in_executor(None, get_earnings_surprises,     ticker),
    )

    s1, r1 = _analyze_target(target)
    s2, r2 = _analyze_recommendation_trend(trends)
    s3, r3 = _analyze_upgrades(events)
    s4, r4 = _analyze_eps_surprise(surprises)

    total_score = s1 + s2 + s3 + s4
    reasons = [r for r in [r1, r2, r3, r4] if r]

    logger.info(f"[Finnhub] {ticker} score={total_score} ({'; '.join(reasons) or 'no signal'})")

    return {
        "ticker":       ticker,
        "total_score":  total_score,
        "reasons":      reasons,
        "breakdown": {
            "price_target":         {"score": s1, "reason": r1, "data": target},
            "recommendation_trend": {"score": s2, "reason": r2, "latest": trends[0] if trends else None,
                                     "previous": trends[1] if len(trends) > 1 else None},
            "upgrades_30d":         {"score": s3, "reason": r3, "events": events[:10]},
            "eps_surprise":         {"score": s4, "reason": r4, "latest": surprises[0] if surprises else None},
        },
    }
