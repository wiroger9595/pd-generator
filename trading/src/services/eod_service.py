"""
EOD (End-of-Day) 批次同步服務
每天晚上用 FinMind 抓取當日所有台股的籌碼面與基本面數據，存入 SQLite
"""
import asyncio
from datetime import datetime, timedelta
from src.utils.logger import logger
from src.repositories.finmind_repository import get_finmind_repo
from src.database.db_handler import (
    save_eod_chip_batch,
    save_eod_fundamental_batch,
    init_eod_db,
)


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _last_workday(date_str: str) -> str:
    """回推到上一個工作日（排除週末）"""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


async def sync_tw_eod(date_str: str = None) -> dict:
    """
    批次同步台股 EOD 籌碼面 + 基本面
    1. TaiwanStockInstitutionalInvestors  → 外資/投信/自營 net
    2. TaiwanStockMarginPurchaseShortSale → 融資/融券差額
    3. TaiwanStockShareholding            → 外資持股比例
    4. TaiwanStockMonthRevenue            → 月營收（近兩個月）

    回傳 {"status", "date", "chip_count", "fundamental_count"}
    """
    if not date_str:
        date_str = _today()
    date_str = _last_workday(date_str)

    repo = get_finmind_repo()
    init_eod_db()

    logger.info(f"[EOD] 開始同步台股 EOD 數據，日期: {date_str}")

    # ── 並行抓取四個 FinMind dataset ─────────────────────────────────────
    loop = asyncio.get_event_loop()

    def _fetch_inst():
        return repo.get(
            dataset="TaiwanStockInstitutionalInvestors",
            start_date=date_str,
            end_date=date_str,
        )

    def _fetch_margin():
        return repo.get(
            dataset="TaiwanStockMarginPurchaseShortSale",
            start_date=date_str,
            end_date=date_str,
        )

    def _fetch_share():
        return repo.get(
            dataset="TaiwanStockShareholding",
            start_date=date_str,
            end_date=date_str,
        )

    # 月營收：抓近 60 天確保有資料
    rev_start = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=60)).strftime("%Y-%m-%d")

    def _fetch_rev():
        return repo.get(
            dataset="TaiwanStockMonthRevenue",
            start_date=rev_start,
            end_date=date_str,
        )

    inst_df, margin_df, share_df, rev_df = await asyncio.gather(
        loop.run_in_executor(None, _fetch_inst),
        loop.run_in_executor(None, _fetch_margin),
        loop.run_in_executor(None, _fetch_share),
        loop.run_in_executor(None, _fetch_rev),
    )

    # ── 整合籌碼面 ───────────────────────────────────────────────────────
    chip_map: dict = {}  # ticker → record

    # 外資/投信/自營
    if inst_df is not None and not inst_df.empty:
        # 欄位: stock_id, stock_name, date, name(外資/投信/自營), buy, sell
        for _, row in inst_df.iterrows():
            tid = str(row.get("stock_id", ""))
            if not tid:
                continue
            if tid not in chip_map:
                chip_map[tid] = {
                    "date": date_str,
                    "ticker": tid,
                    "name": str(row.get("stock_name", tid)),
                    "foreign_net": 0.0,
                    "trust_net": 0.0,
                    "dealer_net": 0.0,
                    "margin_diff": 0.0,
                    "short_diff": 0.0,
                    "foreign_shareholding_pct": 0.0,
                }
            investor = str(row.get("name", ""))
            net = float(row.get("buy", 0)) - float(row.get("sell", 0))
            if "外資" in investor:
                chip_map[tid]["foreign_net"] += net
            elif "投信" in investor:
                chip_map[tid]["trust_net"] += net
            elif "自營" in investor:
                chip_map[tid]["dealer_net"] += net

    # 融資融券
    if margin_df is not None and not margin_df.empty:
        for _, row in margin_df.iterrows():
            tid = str(row.get("stock_id", ""))
            if not tid:
                continue
            if tid not in chip_map:
                chip_map[tid] = {
                    "date": date_str, "ticker": tid,
                    "name": str(row.get("stock_name", tid)),
                    "foreign_net": 0.0, "trust_net": 0.0, "dealer_net": 0.0,
                    "margin_diff": 0.0, "short_diff": 0.0, "foreign_shareholding_pct": 0.0,
                }
            margin_buy = float(row.get("MarginPurchaseBuy", 0))
            margin_sell = float(row.get("MarginPurchaseSell", 0))
            short_sell = float(row.get("ShortSaleSell", 0))
            short_cover = float(row.get("ShortSaleBuy", 0))
            chip_map[tid]["margin_diff"] = margin_buy - margin_sell
            chip_map[tid]["short_diff"] = short_sell - short_cover

    # 外資持股比例
    if share_df is not None and not share_df.empty:
        for _, row in share_df.iterrows():
            tid = str(row.get("stock_id", ""))
            if not tid or tid not in chip_map:
                continue
            pct = float(row.get("ForeignInvestmentSharesRatio", 0))
            chip_map[tid]["foreign_shareholding_pct"] = pct

    chip_records = list(chip_map.values())
    if chip_records:
        save_eod_chip_batch(chip_records, date_str)
        logger.info(f"[EOD] 籌碼面儲存完成：{len(chip_records)} 檔")

    # ── 整合基本面（月營收）────────────────────────────────────────────────
    fund_records = []
    if rev_df is not None and not rev_df.empty:
        # 欄位: stock_id, stock_name, date, revenue, revenue_year, revenue_month
        # 取每檔最新兩筆算 YoY / MoM
        rev_df = rev_df.sort_values("date", ascending=False)
        for tid, grp in rev_df.groupby("stock_id"):
            rows = grp.reset_index(drop=True)
            if len(rows) < 1:
                continue
            latest = rows.iloc[0]
            rev = float(latest.get("revenue", 0))
            rev_yoy = float(latest.get("revenue_year_over_year", 0)) if "revenue_year_over_year" in rows.columns else 0.0
            rev_mom = float(latest.get("revenue_month_over_month", 0)) if "revenue_month_over_month" in rows.columns else 0.0

            # FinMind 有時欄位叫 revenue_last_year / revenue_last_month
            if rev_yoy == 0 and len(rows) >= 2:
                prev_rev = float(rows.iloc[1].get("revenue", 0))
                rev_mom = ((rev - prev_rev) / prev_rev * 100) if prev_rev else 0.0

            fund_records.append({
                "date": date_str,
                "ticker": str(tid),
                "name": str(latest.get("stock_name", tid)),
                "revenue": rev,
                "revenue_yoy": rev_yoy,
                "revenue_mom": rev_mom,
            })

        if fund_records:
            save_eod_fundamental_batch(fund_records, date_str)
            logger.info(f"[EOD] 基本面儲存完成：{len(fund_records)} 檔")

    return {
        "status": "success",
        "date": date_str,
        "chip_count": len(chip_records),
        "fundamental_count": len(fund_records),
    }
