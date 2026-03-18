import time
import asyncio
from concurrent.futures import ThreadPoolExecutor

import talib
import numpy as np
import pandas as pd

from src.data.data_providers import AlphaVantageProvider, PolygonProvider, TiingoProvider, FinMindProvider
from src.utils.logger import logger
from config import US_CONFIG


PROVIDER_MAP = {
    "alpha_vantage": AlphaVantageProvider,
    "polygon": PolygonProvider,
    "tiingo": TiingoProvider,
}


def _score_stock(df, ticker: str) -> dict | None:
    """
    評分制推薦策略 — 不要求「四維全通」，而是逐項給分，
    總分 >= 25 即納入推薦候選。

    評分維度:
      趨勢 (0~30)  — 均線多頭排列 / 價格位置
      量能 (0~25)  — 爆量 / 量比
      指標 (0~30)  — RSI 強勢或超跌反彈 + MACD
      型態 (0~20)  — 突破近期高點 / 接近高點
      動能 (0~10)  — 日漲幅 / 連漲
    """
    if df is None or len(df) < 20:
        return None

    try:
        close = df["Close"].astype(float)
        high = df["High"].astype(float)
        low = df["Low"].astype(float)
        volume = df["Volume"].fillna(0).astype(float)

        curr_p = close.iloc[-1]
        curr_v = volume.iloc[-1]
        if curr_p <= 0:
            return None

        score = 0
        reasons = []

        # ——— 趨勢 (max 30) ———
        sma20 = talib.SMA(close, timeperiod=20)
        sma20_val = sma20.iloc[-1] if not np.isnan(sma20.iloc[-1]) else curr_p

        if len(close) >= 60:
            sma60 = talib.SMA(close, timeperiod=60)
            sma60_val = sma60.iloc[-1] if not np.isnan(sma60.iloc[-1]) else curr_p
            if curr_p > sma20_val > sma60_val:
                score += 30
                reasons.append("趨勢:強多頭排列")
            elif curr_p > sma20_val:
                score += 20
                reasons.append("趨勢:站上MA20")
            elif curr_p > sma60_val:
                score += 10
                reasons.append("趨勢:站上MA60")
            else:
                # 空頭市場 — 檢查是否正在止跌回穩
                ma20_slope = sma20.iloc[-1] - sma20.iloc[-5] if len(sma20) >= 5 else 0
                if ma20_slope > 0:
                    score += 5
                    reasons.append("趨勢:MA20拐頭向上")
        else:
            if not np.isnan(sma20_val) and curr_p > sma20_val:
                score += 20
                reasons.append("趨勢:站上MA20")

        # ——— 量能 (max 25) ———
        if len(volume) >= 20:
            vol_sma20 = talib.SMA(volume, timeperiod=20)
            curr_vol_ma = vol_sma20.iloc[-1]
        else:
            curr_vol_ma = volume.mean()

        if curr_vol_ma > 0:
            vol_ratio = curr_v / curr_vol_ma
            if vol_ratio >= 2.0:
                score += 25
                reasons.append(f"量能:爆量{vol_ratio:.1f}倍")
            elif vol_ratio >= 1.5:
                score += 15
                reasons.append(f"量能:放量{vol_ratio:.1f}倍")
            elif vol_ratio >= 1.0:
                score += 8
                reasons.append(f"量能:正常{vol_ratio:.1f}倍")
            elif vol_ratio >= 0.7:
                score += 3
                reasons.append(f"量能:偏低{vol_ratio:.1f}倍")

        # ——— 指標 (max 30) ———
        rsi = talib.RSI(close, timeperiod=14)
        curr_rsi = rsi.iloc[-1] if not np.isnan(rsi.iloc[-1]) else 50
        prev_rsi = rsi.iloc[-2] if len(rsi) >= 2 and not np.isnan(rsi.iloc[-2]) else curr_rsi

        if 50 <= curr_rsi <= 70:
            score += 15
            reasons.append(f"RSI:{curr_rsi:.0f}(強勢)")
        elif 40 <= curr_rsi < 50:
            score += 8
            reasons.append(f"RSI:{curr_rsi:.0f}(中性偏強)")
        elif 30 <= curr_rsi < 40 and curr_rsi > prev_rsi:
            # 超跌反彈訊號
            score += 12
            reasons.append(f"RSI:{curr_rsi:.0f}(超跌反彈)")
        elif curr_rsi < 30 and curr_rsi > prev_rsi:
            score += 15
            reasons.append(f"RSI:{curr_rsi:.0f}(嚴重超跌反彈)")
        elif curr_rsi > 70:
            score += 5
            reasons.append(f"RSI:{curr_rsi:.0f}(超買)")

        if len(close) >= 26:
            macd, signal, hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
            if not np.isnan(macd.iloc[-1]) and not np.isnan(signal.iloc[-1]):
                if macd.iloc[-1] > signal.iloc[-1]:
                    score += 10
                    reasons.append("MACD:多頭")
                elif len(hist) >= 2 and hist.iloc[-1] > hist.iloc[-2]:
                    # MACD 柱狀體縮小 = 空方力道減弱
                    score += 5
                    reasons.append("MACD:空方減弱")

        # ——— 型態 (max 20) ———
        lookback = min(20, len(high) - 1)
        if lookback >= 5:
            past_high = high.iloc[-(lookback + 1):-1].max()
            past_low = low.iloc[-(lookback + 1):-1].min()
            if curr_p > past_high:
                score += 20
                reasons.append(f"突破{lookback}日新高")
            elif curr_p > past_high * 0.98:
                score += 10
                reasons.append(f"接近{lookback}日新高")
            elif past_low > 0 and curr_p < past_low * 1.03:
                # 接近區間低點 — 潛在支撐反彈
                score += 8
                reasons.append(f"接近{lookback}日支撐位")

        # ——— 動能加分 (max 10) ———
        if len(close) >= 2:
            daily_change = (curr_p - close.iloc[-2]) / close.iloc[-2]
            if daily_change > 0.03:
                score += 10
                reasons.append(f"日漲幅:{daily_change:.1%}")
            elif daily_change > 0.01:
                score += 5
                reasons.append(f"日漲幅:{daily_change:.1%}")

        # 連漲天數加分
        if len(close) >= 4:
            consec_up = 0
            for i in range(-1, max(-5, -len(close)), -1):
                if close.iloc[i] > close.iloc[i - 1]:
                    consec_up += 1
                else:
                    break
            if consec_up >= 3:
                score += 5
                reasons.append(f"連漲{consec_up}天")

        if score < 25:
            return None

        # 計算建議進場價與目標價
        try:
            import pandas_ta as ta
            bb = ta.bbands(close, length=20, std=2)
            if bb is not None and len(bb) > 0:
                entry_price = round(curr_p * 0.985, 2)
                take_profit = round(float(bb.iloc[-1, 2]), 2)  # upper band
            else:
                entry_price = round(curr_p * 0.985, 2)
                take_profit = round(curr_p * 1.05, 2)
        except Exception:
            entry_price = round(curr_p * 0.985, 2)
            take_profit = round(curr_p * 1.05, 2)

        return {
            "ticker": ticker,
            "price": round(curr_p, 2),
            "entry_price": entry_price,
            "take_profit": take_profit,
            "score": score,
            "reason": " | ".join(reasons),
        }

    except Exception as e:
        logger.debug(f"[Recommend] {ticker} scoring error: {e}")
        return None


def _scan_single_stock(provider, ticker: str) -> dict | None:
    """同步掃描單一股票：取歷史資料 → 評分 → 回傳結果或 None"""
    try:
        # 用 120 天確保拿到足夠的交易日數據 (≥60 根 K 線)
        df = provider.get_history(ticker, days=120)
        if df is None:
            return None
        return _score_stock(df, ticker)
    except Exception as e:
        logger.debug(f"[Recommend] {ticker} scan error: {e}")
        return None


async def get_provider_recommendations(
    provider_name: str,
    top_n: int = 5,
    max_scan: int = 25,
    stock_list: list | None = None,
):
    """
    使用指定的單一 Provider 掃描美股清單，回傳 Top-N 推薦。

    Args:
        provider_name: 'alpha_vantage' or 'polygon'
        top_n: 回傳前幾檔推薦
        max_scan: 最多掃描幾檔（保護 API 額度）
        stock_list: 自訂股票清單 [{'ticker': ...}]，None 則自動抓取

    Returns:
        dict with status, provider, scanned, recommendations
    """
    if provider_name not in PROVIDER_MAP:
        return {
            "status": "error",
            "provider": provider_name,
            "error": f"Unsupported provider. Use one of {list(PROVIDER_MAP.keys())}",
        }

    provider = PROVIDER_MAP[provider_name]()

    # 確認 API key 存在
    if not provider.api_key:
        return {
            "status": "error",
            "provider": provider_name,
            "error": f"API key not configured for {provider_name}",
        }

    # 取得股票清單
    if stock_list is None:
        from src.stock.crawler import get_us_stock_list
        stock_list = get_us_stock_list()

    # 限制掃描數量
    scan_list = stock_list[:max_scan]
    logger.info(
        f"[Recommend] Starting {provider_name} scan: "
        f"{len(scan_list)}/{len(stock_list)} stocks, top_n={top_n}"
    )

    results = []
    scanned = 0
    skipped_cooldown = 0

    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=1)

    for stock in scan_list:
        ticker = stock["ticker"]

        # 若 provider 進入 cooldown 就提前中止
        if hasattr(provider, "is_cooled_down") and provider.is_cooled_down:
            logger.warning(
                f"[Recommend] {provider_name} entered cooldown, stopping scan."
            )
            skipped_cooldown = len(scan_list) - scanned
            break

        scanned += 1
        result = await loop.run_in_executor(
            executor, _scan_single_stock, provider, ticker
        )
        if result is not None:
            results.append(result)

    # 按 score 排序取 Top-N
    results.sort(key=lambda x: x["score"], reverse=True)
    top_results = results[:top_n]

    logger.info(
        f"[Recommend] {provider_name} done: scanned={scanned}, "
        f"matched={len(results)}, top_n={len(top_results)}, "
        f"skipped_cooldown={skipped_cooldown}"
    )

    return {
        "status": "success",
        "provider": provider_name,
        "scanned": scanned,
        "matched": len(results),
        "skipped_cooldown": skipped_cooldown,
        "recommendations": top_results,
    }


async def get_tw_recommendations(
    top_n: int = 5,
    max_scan: int = 30,
    stock_list: list | None = None,
) -> dict:
    """使用 FinMind 掃描台股，回傳 Top-N 推薦。"""
    provider = FinMindProvider()

    if not provider.api_key:
        return {"status": "error", "provider": "finmind", "error": "FINMIND_API_KEY not configured"}

    if stock_list is None:
        from src.stock.crawler import get_tw_stock_list
        stock_list = get_tw_stock_list()

    scan_list = stock_list[:max_scan]
    logger.info(f"[Recommend] Starting finmind TW scan: {len(scan_list)}/{len(stock_list)} stocks, top_n={top_n}")

    results = []
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=1)

    for stock in scan_list:
        ticker = stock["ticker"]
        result = await loop.run_in_executor(executor, _scan_single_stock, provider, ticker)
        if result is not None:
            result["name"] = stock.get("name", ticker)
            results.append(result)

    results.sort(key=lambda x: x["score"], reverse=True)
    top_results = results[:top_n]

    logger.info(f"[Recommend] finmind TW done: scanned={len(scan_list)}, matched={len(results)}, top_n={len(top_results)}")

    return {
        "status": "success",
        "provider": "finmind",
        "scanned": len(scan_list),
        "matched": len(results),
        "recommendations": top_results,
    }


async def run_daily_analysis(top_n: int = 5, max_scan_us: int = 20, max_scan_tw: int = 30) -> dict:
    """
    每日分析主函式：
    - 美股：依序跑 AlphaVantage、Polygon、Tiingo，合併結果（多家 provider 同時推薦 → 加分）
    - 台股：FinMind
    - 結果發送至 LINE
    """
    from src.utils.notifier import send_combined_report

    # --- 美股：三大 provider 依序掃描（避免同時觸發 rate limit） ---
    us_merged: dict[str, dict] = {}
    for provider_name in ["polygon", "alpha_vantage", "tiingo"]:
        result = await get_provider_recommendations(provider_name, top_n=top_n * 2, max_scan=max_scan_us)
        if result.get("status") != "success":
            logger.warning(f"[DailyAnalysis] {provider_name} failed: {result.get('error', 'unknown')}")
            continue
        for rec in result.get("recommendations", []):
            ticker = rec["ticker"]
            if ticker not in us_merged:
                us_merged[ticker] = {**rec, "provider_count": 1, "providers": [provider_name]}
            else:
                # 多家 provider 同時推薦 → score 加分
                us_merged[ticker]["score"] = max(us_merged[ticker]["score"], rec["score"]) + 15
                us_merged[ticker]["provider_count"] += 1
                us_merged[ticker]["providers"].append(provider_name)
                # 合併推薦理由
                existing_reason = us_merged[ticker].get("reason", "")
                new_reason = rec.get("reason", "")
                if new_reason and new_reason not in existing_reason:
                    us_merged[ticker]["reason"] = f"{existing_reason} | {new_reason}" if existing_reason else new_reason

    us_top = sorted(us_merged.values(), key=lambda x: x["score"], reverse=True)[:top_n]

    # --- 台股：FinMind ---
    tw_result = await get_tw_recommendations(top_n=top_n, max_scan=max_scan_tw)
    tw_top = tw_result.get("recommendations", [])

    # --- 轉換格式 → notifier ---
    def _to_notifier(recs):
        out = []
        for r in recs:
            providers_str = "/".join(r.get("providers", [])) if r.get("providers") else "single"
            reason = r.get("reason", "技術訊號")
            if r.get("provider_count", 1) > 1:
                reason = f"[{r['provider_count']}家確認:{providers_str}] {reason}"
            out.append({
                "ticker": r["ticker"],
                "name": r.get("name", r["ticker"]),
                "price": r["price"],
                "buy_points": {"score": r["score"], "reason": reason},
            })
        return out

    send_combined_report("美股 (AV/Polygon/Tiingo)", _to_notifier(us_top), [], [])
    send_combined_report("台股 (FinMind)", _to_notifier(tw_top), [], [])

    logger.info(f"[DailyAnalysis] 完成：美股推薦 {len(us_top)} 檔，台股推薦 {len(tw_top)} 檔")
    return {
        "us": {"scanned_providers": 3, "recommendations": us_top},
        "tw": {"provider": "finmind", "recommendations": tw_top},
    }


def _check_sell_single(data_service, ticker: str, entry_price: float | None) -> dict | None:
    """同步：取歷史資料 → 跑 check_sell → 回傳結果或 None"""
    try:
        from src.strategies.comprehensive_strategy import ComprehensiveStrategy
        df = data_service.get_history(ticker, days=90)
        if df is None or len(df) < 30:
            return None
        strategy = ComprehensiveStrategy()
        sell_match, sell_reason = strategy.check_sell(df, entry_price)
        if not sell_match:
            return None
        return {
            "ticker": ticker,
            "price": round(float(df["Close"].iloc[-1]), 2),
            "entry_price": entry_price,
            "sell_reason": sell_reason,
        }
    except Exception as e:
        logger.debug(f"[SellScan] {ticker} error: {e}")
        return None


async def get_sell_recommendations(market: str) -> dict:
    """
    掃描庫存 + 近期觀察名單，找出賣出訊號，結果發送至 LINE。

    Args:
        market: 'us' 或 'tw'
    """
    from src.database.db_handler import get_active_tickers
    from src.data.data_service import DataService
    from src.utils.notifier import send_combined_report

    market = market.lower()
    monitor = get_active_tickers(market)
    holdings = monitor["holdings"]       # [{"ticker", "entry_price", "name", ...}]
    watched = monitor["watched"]         # [{"ticker", "name", "price"}]

    # 合併清單，庫存優先（有 entry_price）
    all_targets = {}
    for h in holdings:
        all_targets[h["ticker"]] = {"name": h.get("name", h["ticker"]), "entry_price": h.get("entry_price")}
    for w in watched:
        if w["ticker"] not in all_targets:
            all_targets[w["ticker"]] = {"name": w.get("name", w["ticker"]), "entry_price": None}

    if not all_targets:
        logger.info(f"[SellScan] {market.upper()} 無庫存/觀察名單，略過")
        return {"status": "ok", "market": market.upper(), "sell_signals": []}

    logger.info(f"[SellScan] {market.upper()} 開始掃描 {len(all_targets)} 檔...")

    data_service = DataService()
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=1)

    sell_results = []
    for ticker, info in all_targets.items():
        result = await loop.run_in_executor(
            executor, _check_sell_single, data_service, ticker, info["entry_price"]
        )
        if result is not None:
            result["name"] = info["name"]
            result["is_holding"] = info["entry_price"] is not None
            sell_results.append(result)

    # 分拆庫存賣訊 vs 觀察名單賣訊
    sell_holdings = [r for r in sell_results if r["is_holding"]]
    sell_watched = [r for r in sell_results if not r["is_holding"]]

    # 轉換成 notifier 格式
    def _fmt(items):
        return [{
            "ticker": r["ticker"],
            "name": r["name"],
            "price": r["price"],
            "sell_reason": r["sell_reason"],
        } for r in items]

    market_label = "美股" if market == "us" else "台股"
    send_combined_report(f"{market_label} 賣出掃描", [], _fmt(sell_holdings), _fmt(sell_watched))

    logger.info(f"[SellScan] {market.upper()} 完成：庫存賣訊 {len(sell_holdings)} | 觀察賣訊 {len(sell_watched)}，已發 LINE")
    return {
        "status": "ok",
        "market": market.upper(),
        "sell_holdings": sell_holdings,
        "sell_watched": sell_watched,
    }
