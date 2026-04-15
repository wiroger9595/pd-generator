"""
全方位股票分析服務 — 整合四個面向
流程：
  1. 籌碼面 — 讀 EOD SQLite 快取（當日已 sync，無 API 額度消耗）
  2. 基本面 — 讀 EOD SQLite 快取
  3. 技術面 — 呼叫 Alpha Vantage RSI / KD / MACD
  4. 消息面 — Google News RSS + Gemini AI 情緒分析
回傳統一的 overall_score + signal + 各面向明細
"""
import asyncio
from datetime import datetime
from src.utils.logger import logger
from src.database.db_handler import get_eod_chip, get_eod_fundamental


# ── 面向評分函式 ──────────────────────────────────────────────────────────

def _score_chip(chip: dict) -> tuple[int, str]:
    """從 EOD 快取計算籌碼面分數"""
    if not chip:
        return 0, "無籌碼快取（請先執行 /api/eod/sync/tw）"

    score = 0
    reasons = []

    foreign_net = chip.get("foreign_net", 0)
    trust_net   = chip.get("trust_net", 0)
    dealer_net  = chip.get("dealer_net", 0)
    margin_diff = chip.get("margin_diff", 0)
    short_diff  = chip.get("short_diff", 0)
    share_pct   = chip.get("foreign_shareholding_pct", 0)

    # 外資
    if foreign_net > 10000:
        score += 25; reasons.append(f"外資大買 {foreign_net:+.0f}")
    elif foreign_net > 3000:
        score += 15; reasons.append(f"外資淨買 {foreign_net:+.0f}")
    elif foreign_net < -10000:
        score -= 25; reasons.append(f"外資大賣 {foreign_net:+.0f}")
    elif foreign_net < -3000:
        score -= 15; reasons.append(f"外資淨賣 {foreign_net:+.0f}")

    # 投信
    if trust_net > 1000:
        score += 15; reasons.append(f"投信買超 {trust_net:+.0f}")
    elif trust_net < -1000:
        score -= 10; reasons.append(f"投信賣超 {trust_net:+.0f}")

    # 自營
    if dealer_net > 500:
        score += 5; reasons.append(f"自營買超 {dealer_net:+.0f}")
    elif dealer_net < -500:
        score -= 5; reasons.append(f"自營賣超 {dealer_net:+.0f}")

    # 融資（散戶槓桿）
    if margin_diff > 1000:
        score += 5; reasons.append("融資增加（散戶追多）")
    elif margin_diff < -1000:
        score -= 5; reasons.append("融資減少（散戶退場）")

    # 融券（放空壓力）
    if short_diff > 500:
        score -= 10; reasons.append(f"融券增加 {short_diff:+.0f}（放空增加）")
    elif short_diff < -500:
        score += 5; reasons.append(f"融券回補 {short_diff:+.0f}")

    # 外資持股比例
    if share_pct >= 70:
        score += 10; reasons.append(f"外資持股高 {share_pct:.1f}%")
    elif share_pct <= 20:
        score -= 5; reasons.append(f"外資持股低 {share_pct:.1f}%")

    reason = " | ".join(reasons) if reasons else "籌碼面無明顯訊號"
    return score, reason


def _score_fundamental(fund: dict) -> tuple[int, str]:
    """從 EOD 快取計算基本面分數"""
    if not fund:
        return 0, "無基本面快取（請先執行 /api/eod/sync/tw）"

    score = 0
    reasons = []
    revenue_yoy = fund.get("revenue_yoy", 0)
    revenue_mom = fund.get("revenue_mom", 0)
    revenue     = fund.get("revenue", 0)

    if revenue_yoy >= 30:
        score += 30; reasons.append(f"月營收年增 {revenue_yoy:.1f}%（強勁成長）")
    elif revenue_yoy >= 15:
        score += 20; reasons.append(f"月營收年增 {revenue_yoy:.1f}%")
    elif revenue_yoy >= 5:
        score += 10; reasons.append(f"月營收年增 {revenue_yoy:.1f}%")
    elif revenue_yoy < -20:
        score -= 25; reasons.append(f"月營收年減 {revenue_yoy:.1f}%（衰退）")
    elif revenue_yoy < -5:
        score -= 15; reasons.append(f"月營收年減 {revenue_yoy:.1f}%")

    if revenue_mom >= 10:
        score += 10; reasons.append(f"月營收月增 {revenue_mom:.1f}%")
    elif revenue_mom < -10:
        score -= 10; reasons.append(f"月營收月減 {revenue_mom:.1f}%")

    reason = " | ".join(reasons) if reasons else "基本面無明顯變化"
    return score, reason


def _score_technical(tech: dict) -> tuple[int, str]:
    """從 Alpha Vantage 結果計算技術面分數"""
    if not tech or tech.get("status") not in ("success",):
        return 0, "技術指標無數據（Alpha Vantage 未回應或已超過配額）"
    return tech.get("score", 0), tech.get("reason", "無訊號")


def _score_news(news: dict) -> tuple[int, str]:
    """從 Gemini AI 情緒分析計算消息面分數"""
    if not news or news.get("status") not in ("success",):
        return 0, "無法取得新聞情緒"
    raw_score = int(news.get("score", 0))
    # 將 Gemini 回傳的 -100~100 縮放至 -40~40
    scaled = int(raw_score * 0.4)
    summary = news.get("summary", "")
    return scaled, summary or "消息面無明顯情緒"


def _overall_signal(score: int) -> str:
    if score >= 40:
        return "strong_buy"
    if score >= 20:
        return "buy"
    if score <= -40:
        return "strong_sell"
    if score <= -20:
        return "sell"
    return "neutral"


# ── 主要服務函式 ──────────────────────────────────────────────────────────

async def get_tw_full_analysis(ticker: str, name: str = "") -> dict:
    """
    台股全方位四維分析
    ticker: 純數字代號，如 2330
    """
    from src.services.technical_service import get_technical_indicators
    from src.services.ai_news_service import analyze_tw_news_sentiment

    logger.info(f"[FullAnalysis] 開始台股 {ticker} 全方位分析")
    today = datetime.now().strftime("%Y-%m-%d")

    # ① 籌碼面 + 基本面 — 從 SQLite 快取讀取（不消耗 API 額度）
    chip_data = get_eod_chip(ticker)
    fund_data = get_eod_fundamental(ticker)

    if name == "" and chip_data.get("name"):
        name = chip_data["name"]
    elif name == "" and fund_data.get("name"):
        name = fund_data["name"]

    # ② 技術面（Alpha Vantage）+ 消息面（Google News + Gemini）— 並行
    tech_result, news_result = await asyncio.gather(
        get_technical_indicators(symbol=ticker, market="tw"),
        analyze_tw_news_sentiment(ticker=ticker, name=name),
    )

    # ── 評分整合 ─────────────────────────────────────────────────────────
    chip_score,  chip_reason  = _score_chip(chip_data)
    fund_score,  fund_reason  = _score_fundamental(fund_data)
    tech_score,  tech_reason  = _score_technical(tech_result)
    news_score,  news_reason  = _score_news(news_result)

    overall = chip_score + fund_score + tech_score + news_score
    signal  = _overall_signal(overall)

    logger.info(
        f"[FullAnalysis] {ticker} overall={overall} signal={signal} "
        f"chip={chip_score} fund={fund_score} tech={tech_score} news={news_score}"
    )

    return {
        "status": "success",
        "ticker": ticker,
        "name": name,
        "market": "TW",
        "date": today,
        "overall_score": overall,
        "signal": signal,
        "dimensions": {
            "chip": {
                "score": chip_score,
                "reason": chip_reason,
                "data": chip_data or None,
            },
            "fundamental": {
                "score": fund_score,
                "reason": fund_reason,
                "data": fund_data or None,
            },
            "technical": {
                "score": tech_score,
                "reason": tech_reason,
                "indicators": tech_result.get("indicators") if tech_result else None,
            },
            "news": {
                "score": news_score,
                "reason": news_reason,
                "sentiment": news_result.get("sentiment") if news_result else None,
                "key_factors": news_result.get("key_factors", []) if news_result else [],
                "headlines": news_result.get("headlines", []) if news_result else [],
            },
        },
    }


async def get_us_full_analysis(ticker: str, name: str = "") -> dict:
    """
    美股全方位三維分析
    （美股無 FinMind EOD 快取，籌碼面改用 Polygon volume ratio）
    """
    from src.services.technical_service import get_technical_indicators
    from src.services.ai_news_service import analyze_us_news_sentiment

    logger.info(f"[FullAnalysis] 開始美股 {ticker} 全方位分析")
    today = datetime.now().strftime("%Y-%m-%d")

    # ① 技術面 + 消息面 — 並行
    tech_result, news_result = await asyncio.gather(
        get_technical_indicators(symbol=ticker, market="us"),
        analyze_us_news_sentiment(ticker=ticker, name=name),
    )

    # ② 籌碼面 — Polygon volume ratio（美股無融資融券，用成交量異常代替）
    chip_score, chip_reason = _score_us_volume(ticker)

    tech_score, tech_reason = _score_technical(tech_result)
    news_score, news_reason = _score_news(news_result)

    overall = chip_score + tech_score + news_score
    signal  = _overall_signal(overall)

    return {
        "status": "success",
        "ticker": ticker,
        "name": name,
        "market": "US",
        "date": today,
        "overall_score": overall,
        "signal": signal,
        "dimensions": {
            "chip": {
                "score": chip_score,
                "reason": chip_reason,
            },
            "technical": {
                "score": tech_score,
                "reason": tech_reason,
                "indicators": tech_result.get("indicators") if tech_result else None,
            },
            "news": {
                "score": news_score,
                "reason": news_reason,
                "sentiment": news_result.get("sentiment") if news_result else None,
                "key_factors": news_result.get("key_factors", []) if news_result else [],
                "headlines": news_result.get("headlines", []) if news_result else [],
            },
        },
    }


def _score_us_volume(ticker: str) -> tuple[int, str]:
    """美股籌碼替代指標：Polygon 成交量比率"""
    try:
        from src.repositories.polygon_repository import get_polygon_repo
        repo = get_polygon_repo()
        vol_ratio, price_chg, avg_vol = repo.volume_signal(ticker)
        score = 0
        reason_parts = []
        if vol_ratio >= 2.5:
            score += 20; reason_parts.append(f"爆量 vol_ratio={vol_ratio:.1f}x")
        elif vol_ratio >= 1.5:
            score += 10; reason_parts.append(f"量增 vol_ratio={vol_ratio:.1f}x")
        if price_chg >= 3:
            score += 10; reason_parts.append(f"強勢 +{price_chg:.1f}%")
        elif price_chg <= -3:
            score -= 10; reason_parts.append(f"弱勢 {price_chg:.1f}%")
        return score, " | ".join(reason_parts) or "成交量正常"
    except Exception as e:
        logger.warning(f"[FullAnalysis] US volume signal failed: {e}")
        return 0, "無法取得成交量數據"
