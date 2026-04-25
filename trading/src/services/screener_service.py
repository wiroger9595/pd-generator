"""
主動選股服務 — 掃描全市場，找出多維共振的最佳標的
台股：EOD 快取 → 技術面(FinMind) → 新聞面(Google+Gemini)
美股：Polygon 量能 → 技術面(多provider) → 新聞面(Google+Gemini)
全程背景執行，結果透過 LINE 發送
"""
import asyncio
from src.utils.logger import logger
from src.services.full_analysis_service import (
    _score_chip, _score_fundamental, _score_news, _score_analyst, _overall_signal
)
from src.database.db_handler import get_all_eod_chip, get_all_eod_fundamental


# ─────────────────────────────────────────────────────────────────────────────
# 台股掃描
# ─────────────────────────────────────────────────────────────────────────────

async def screen_tw_stocks(top_n: int = 5) -> dict:
    """
    台股選股流程：
    0. 預篩：TWSE + TPEX OpenAPI 全市場動能排序，取前 80 高動能標的
    1. 讀 EOD 快取，對候選股計算籌碼面 + 基本面分數（零 API）
    2. 篩出分數 ≥ 15 的候選（通常 10–30 檔）
    3. 對候選股並行跑：技術面(FinMind) + 消息面(Google+Gemini)
    4. 四維合併排序，取 top_n 檔

    注意：若 EOD 快取為空，改用即時掃描（動能預篩結果傳入）
    """
    logger.info("[Screener] 開始台股選股...")

    # ── Phase 0：全市場動能預篩 ────────────────────────────────────────────
    from src.stock.crawler import get_tw_market_movers
    loop = asyncio.get_event_loop()
    movers = await loop.run_in_executor(None, lambda: get_tw_market_movers(top_n=80))
    movers_set = {m["ticker"].replace(".TW", "").replace(".TWO", "") for m in movers}
    if movers:
        logger.info(f"[Screener] TW 全市場預篩: {len(movers)} 檔高動能候選")

    # ── Phase 1：EOD 快取預篩 ──────────────────────────────────────────────
    all_chip  = get_all_eod_chip()
    all_fund  = get_all_eod_fundamental()

    if all_chip or all_fund:
        # 優先處理在動能名單中的股票
        if movers_set:
            all_chip_sorted = sorted(
                all_chip,
                key=lambda r: (r.get("ticker", "").replace(".TW", "").replace(".TWO", "") in movers_set),
                reverse=True,
            )
            all_fund_sorted = sorted(
                all_fund,
                key=lambda r: (r.get("ticker", "").replace(".TW", "").replace(".TWO", "") in movers_set),
                reverse=True,
            )
        else:
            all_chip_sorted, all_fund_sorted = all_chip, all_fund
        candidates = await _tw_screen_from_cache(all_chip_sorted, all_fund_sorted, top_n)
    else:
        logger.info("[Screener] EOD 快取為空，改用即時掃描")
        candidates = await _tw_screen_live(top_n, stock_list=movers or None)

    return {
        "status": "success",
        "market": "TW",
        "total_candidates": len(candidates),
        "top_n": top_n,
        "results": candidates[:top_n],
    }


async def _tw_screen_from_cache(all_chip: list, all_fund: list, top_n: int) -> list:
    """Phase 1+2：從 EOD 快取篩選，再對候選股跑技術+新聞"""
    # 合併 chip + fundamental 成 ticker→record 的 dict
    chip_map = {r["ticker"]: r for r in all_chip}
    fund_map = {r["ticker"]: r for r in all_fund}

    # 對每檔計算 chip + fund 分數
    pre_scored = []
    all_tickers = set(chip_map) | set(fund_map)
    for ticker in all_tickers:
        chip = chip_map.get(ticker, {})
        fund = fund_map.get(ticker, {})
        c_score, c_reason = _score_chip(chip)
        f_score, f_reason = _score_fundamental(fund)
        pre_total = c_score + f_score
        name = chip.get("name") or fund.get("name") or ticker
        pre_scored.append({
            "ticker": ticker,
            "name": name,
            "chip_score": c_score,
            "chip_reason": c_reason,
            "fund_score": f_score,
            "fund_reason": f_reason,
            "pre_total": pre_total,
            "chip_data": chip,
            "fund_data": fund,
        })

    # 只保留籌碼+基本面分數 ≥ 15 的候選
    pre_scored = [s for s in pre_scored if s["pre_total"] >= 15]
    pre_scored.sort(key=lambda x: x["pre_total"], reverse=True)
    candidates = pre_scored[:20]  # 最多取 20 檔進第二階段

    if not candidates:
        logger.info("[Screener] EOD 快取無合格候選")
        return []

    logger.info(f"[Screener] Phase1 候選 {len(candidates)} 檔，進行技術+新聞分析")

    # ── Phase 2：技術面 + 新聞面（並行）─────────────────────────────────
    from src.services.recommendation_service import get_tw_recommendations
    from src.services.ai_news_service import analyze_tw_news_sentiment

    # 技術面：用 FinMind-based 推薦服務（無 AV 限制）
    tech_result = await _safe(get_tw_recommendations(top_n=50, max_scan=50))
    tech_map: dict = {}
    for rec in (tech_result.get("recommendations", []) if tech_result else []):
        t = rec.get("ticker", "")
        tid = t.replace(".TW", "").replace(".TWO", "")
        tech_map[tid] = {
            "score": rec.get("score", 0),
            "reason": rec.get("reason", ""),
        }

    # 新聞面：對候選股批次分析（並行）
    news_tasks = [
        analyze_tw_news_sentiment(ticker=s["ticker"], name=s["name"])
        for s in candidates
    ]
    news_results = await asyncio.gather(*news_tasks, return_exceptions=True)

    # ── 合併四維 ──────────────────────────────────────────────────────────
    final = []
    for s, news_res in zip(candidates, news_results):
        ticker = s["ticker"]
        tech = tech_map.get(ticker, {})
        t_score = tech.get("score", 0) if tech else 0
        t_reason = tech.get("reason", "技術面未命中") if tech else "技術面未命中"

        if isinstance(news_res, Exception):
            n_score, n_reason = 0, "新聞分析失敗"
            n_headlines = []
        else:
            n_score, n_reason = _score_news(news_res)
            n_headlines = news_res.get("headlines", []) if news_res else []

        total = s["chip_score"] + s["fund_score"] + t_score + n_score
        final.append({
            "ticker": ticker,
            "name": s["name"],
            "overall_score": total,
            "signal": _overall_signal(total),
            "dimensions": {
                "chip":        {"score": s["chip_score"], "reason": s["chip_reason"]},
                "fundamental": {"score": s["fund_score"], "reason": s["fund_reason"]},
                "technical":   {"score": t_score, "reason": t_reason},
                "news":        {"score": n_score, "reason": n_reason, "headlines": n_headlines},
            },
        })

    final.sort(key=lambda x: x["overall_score"], reverse=True)
    return final


async def _tw_screen_live(top_n: int, stock_list: list | None = None) -> list:
    """EOD 快取不存在時的備援：用既有服務即時掃描（較慢）"""
    from src.services.recommendation_service import get_tw_recommendations
    result = await get_tw_recommendations(
        top_n=top_n,
        max_scan=50,
        stock_list=stock_list,  # 傳入動能預篩結果
    )
    raw = result.get("recommendations", [])
    out = []
    for r in raw:
        out.append({
            "ticker": r.get("ticker", ""),
            "name": r.get("name", r.get("ticker", "")),
            "overall_score": r.get("score", 0),
            "signal": _overall_signal(r.get("score", 0)),
            "dimensions": {
                "technical": {"score": r.get("score", 0), "reason": r.get("reason", "")},
            },
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 美股掃描
# ─────────────────────────────────────────────────────────────────────────────

async def screen_us_stocks(top_n: int = 5) -> dict:
    """
    美股選股流程：
    0. 預篩：Polygon grouped daily 全市場動能排序，取前 80 高動能標的
    1. 技術面：三 provider（Polygon / AV / Tiingo）並行精選評分
    2. 候選股：量能 + 技術共振的前 15 名
    3. 消息面：Google News + Gemini 情緒分析
    4. 綜合排序，取 top_n
    """
    logger.info("[Screener] 開始美股選股...")

    from src.services.recommendation_service import get_provider_recommendations
    from src.services.ai_news_service import analyze_us_news_sentiment
    from src.stock.crawler import get_us_market_movers

    # ── Phase 0：全市場動能預篩 ────────────────────────────────────────────
    loop = asyncio.get_event_loop()
    market_universe = await loop.run_in_executor(None, lambda: get_us_market_movers(top_n=80))
    if market_universe:
        logger.info(f"[Screener] 全市場預篩: {len(market_universe)} 檔高動能候選")
    else:
        logger.info("[Screener] 全市場預篩不可用，改用 ETF 持股名單")
        market_universe = None  # fallback to default list in recommendation_service

    # ── Phase 1：三 provider 技術掃描（並行）───────────────────────────────
    # max_scan=50: 從 80 檔動能股中各取 50 支評分（AV 有每日限額，Polygon/Tiingo 無限）
    poly, av, tiingo = await asyncio.gather(
        _safe(get_provider_recommendations("polygon",       top_n=20, max_scan=50, stock_list=market_universe)),
        _safe(get_provider_recommendations("alpha_vantage", top_n=20, max_scan=25, stock_list=market_universe)),
        _safe(get_provider_recommendations("tiingo",        top_n=20, max_scan=50, stock_list=market_universe)),
    )

    # 合併三 provider（同 ticker 取最高分，額外加成）
    merged: dict = {}
    for items, pname in [
        (poly   or {}, "Polygon"),
        (av     or {}, "AV"),
        (tiingo or {}, "Tiingo"),
    ]:
        for rec in items.get("recommendations", []):
            t = rec.get("ticker", "").upper()
            if not t:
                continue
            if t not in merged:
                merged[t] = {**rec, "providers": [pname], "provider_count": 1}
            else:
                merged[t]["score"] = max(merged[t]["score"], rec["score"]) + 10
                merged[t]["providers"].append(pname)
                merged[t]["provider_count"] += 1

    candidates = sorted(merged.values(), key=lambda x: x["score"], reverse=True)[:15]

    if not candidates:
        return {"status": "no_candidates", "market": "US", "results": []}

    logger.info(f"[Screener] 美股技術候選 {len(candidates)} 檔，進行消息+分析師分析")

    # ── Phase 2：Gemini 新聞情緒（並行）+ FMP 分析師評等（executor 並行）──
    from concurrent.futures import ThreadPoolExecutor

    news_tasks = [
        analyze_us_news_sentiment(ticker=c["ticker"], name=c.get("name", ""))
        for c in candidates
    ]
    news_results = await asyncio.gather(*news_tasks, return_exceptions=True)

    # FMP 分析師評等 — 批次同步呼叫（在 executor 避免阻塞事件迴圈）
    fmp_results: list[dict] = []
    try:
        from src.data.fmp_provider import FMPProvider
        fmp = FMPProvider()
        if fmp.api_key:
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=4) as ex:
                fmp_futures = [
                    loop.run_in_executor(ex, fmp.get_analyst_data, c["ticker"])
                    for c in candidates
                ]
                fmp_results = list(await asyncio.gather(*fmp_futures, return_exceptions=True))
        else:
            fmp_results = [{}] * len(candidates)
    except Exception as e:
        logger.warning(f"[Screener] FMP batch failed: {e}")
        fmp_results = [{}] * len(candidates)

    # ── 合併 ─────────────────────────────────────────────────────────────
    final = []
    for c, news_res, fmp_res in zip(candidates, news_results, fmp_results):
        t_score = c.get("score", 0)
        t_reason = c.get("reason", "")

        if isinstance(news_res, Exception):
            n_score, n_reason = 0, "新聞分析失敗"
            n_headlines = []
        else:
            n_score, n_reason = _score_news(news_res)
            n_headlines = news_res.get("headlines", []) if news_res else []

        analyst_data = fmp_res if isinstance(fmp_res, dict) else {}
        current_price = c.get("price", 0)
        a_score, a_reason = _score_analyst(analyst_data, current_price)

        total = t_score + n_score + a_score
        dim: dict = {
            "technical": {"score": t_score, "reason": t_reason},
            "news":      {"score": n_score, "reason": n_reason, "headlines": n_headlines},
        }
        if analyst_data:
            dim["analyst"] = {"score": a_score, "reason": a_reason}

        final.append({
            "ticker": c["ticker"],
            "name": c.get("name", c["ticker"]),
            "overall_score": total,
            "signal": _overall_signal(total),
            "providers": c.get("providers", []),
            "dimensions": dim,
        })

    final.sort(key=lambda x: x["overall_score"], reverse=True)

    return {
        "status": "success",
        "market": "US",
        "total_candidates": len(final),
        "top_n": top_n,
        "results": final[:top_n],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 工具
# ─────────────────────────────────────────────────────────────────────────────

async def _safe(coro):
    try:
        return await coro
    except Exception as e:
        logger.warning(f"[Screener] safe call failed: {e}")
        return {}
