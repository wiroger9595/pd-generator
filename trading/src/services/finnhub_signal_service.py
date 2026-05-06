"""
Finnhub 訊號分析 Service — 免費版可用的兩個 endpoint：
- /stock/recommendation（評等趨勢，含當下絕對水準與月變化）
- /stock/earnings（近 4 季 EPS actual vs estimate）

付費才能用的 /stock/price-target、/stock/upgrade-downgrade 已移除
"""
import asyncio
from src.utils.logger import logger
from src.repositories.finnhub_repository import (
    get_recommendation_trends,
    get_earnings_surprises,
)


def _analyze_recommendation_level(trends: list[dict]) -> tuple[int, str]:
    """評等絕對水準：買進比例 + 總分析師人數"""
    if not trends:
        return 0, ""
    latest = trends[0]
    sb = latest.get("strongBuy", 0) or 0
    b  = latest.get("buy", 0) or 0
    h  = latest.get("hold", 0) or 0
    s  = latest.get("sell", 0) or 0
    ss = latest.get("strongSell", 0) or 0
    total = sb + b + h + s + ss
    if total == 0:
        return 0, ""
    bullish = sb + b
    pct = bullish / total * 100

    score = 0
    if pct >= 90 and total >= 20:
        score = 20
    elif pct >= 80 and total >= 15:
        score = 15
    elif pct >= 70 and total >= 10:
        score = 10
    elif pct >= 60:
        score = 5
    elif pct <= 30:
        score = -10

    if score == 0:
        return 0, ""
    return score, f"買進評等 {bullish}/{total} ({pct:.0f}%)"


def _analyze_recommendation_trend(trends: list[dict]) -> tuple[int, str]:
    """評等月變化：strongBuy + buy 增減"""
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


def _analyze_eps_surprise(surprises: list[dict]) -> tuple[int, str]:
    """近 4 季 EPS surprise：最新季 + 平均"""
    if not surprises:
        return 0, ""

    def _pct(item: dict) -> float | None:
        p = item.get("surprisePercent")
        if p is not None:
            return p
        actual   = item.get("actual") or 0
        estimate = item.get("estimate") or 0
        if not estimate:
            return None
        return (actual - estimate) / abs(estimate) * 100

    latest_pct = _pct(surprises[0])
    pcts = [p for p in (_pct(s) for s in surprises[:4]) if p is not None]
    avg_pct = sum(pcts) / len(pcts) if pcts else None

    if latest_pct is None and avg_pct is None:
        return 0, ""

    score = 0
    reasons = []

    # 最新季加分
    if latest_pct is not None:
        if latest_pct >= 20:
            score += 25; reasons.append(f"最新季 EPS 超預期 {latest_pct:.1f}%")
        elif latest_pct >= 10:
            score += 15; reasons.append(f"最新季 EPS 超預期 {latest_pct:.1f}%")
        elif latest_pct >= 5:
            score += 8;  reasons.append(f"最新季 EPS 超預期 {latest_pct:.1f}%")
        elif latest_pct <= -10:
            score -= 15; reasons.append(f"最新季 EPS 不如預期 {latest_pct:.1f}%")

    # 近 4 季平均（穩定性加分）
    if avg_pct is not None and len(pcts) >= 3:
        if avg_pct >= 10:
            score += 10; reasons.append(f"近 4 季平均超預期 {avg_pct:.1f}%")
        elif avg_pct >= 5:
            score += 5;  reasons.append(f"近 4 季平均超預期 {avg_pct:.1f}%")
        elif avg_pct <= -5:
            score -= 5;  reasons.append(f"近 4 季平均不如預期 {avg_pct:.1f}%")

    if score == 0:
        return 0, ""
    return score, "; ".join(reasons)


async def analyze_finnhub_signals(ticker: str) -> dict:
    """
    並行抓 2 種免費訊號（評等 + EPS），整合分數
    最高約 +70 / 最低約 -40
    """
    ticker = ticker.upper()
    loop = asyncio.get_running_loop()

    trends, surprises = await asyncio.gather(
        loop.run_in_executor(None, get_recommendation_trends, ticker),
        loop.run_in_executor(None, get_earnings_surprises,    ticker),
    )

    s1, r1 = _analyze_recommendation_level(trends)
    s2, r2 = _analyze_recommendation_trend(trends)
    s3, r3 = _analyze_eps_surprise(surprises)

    total_score = s1 + s2 + s3
    reasons = [r for r in [r1, r2, r3] if r]

    logger.info(f"[Finnhub] {ticker} score={total_score} ({'; '.join(reasons) or 'no signal'})")

    return {
        "ticker":       ticker,
        "total_score":  total_score,
        "reasons":      reasons,
        "breakdown": {
            "recommendation_level": {"score": s1, "reason": r1, "latest": trends[0] if trends else None},
            "recommendation_trend": {"score": s2, "reason": r2,
                                     "previous": trends[1] if len(trends) > 1 else None},
            "eps_surprise":         {"score": s3, "reason": r3,
                                     "recent": surprises[:4] if surprises else []},
        },
    }
