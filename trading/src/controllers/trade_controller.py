"""
機器人交易 Controller  —  /api/robot/*
"""
import re

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Request

from src.utils.logger import logger

router = APIRouter(prefix="/api/robot", tags=["Trade"])


@router.post("/trade")
async def robot_trade(
    background_tasks: BackgroundTasks,
    request: Request,
    payload: dict = Body(...),
):
    """指定代號清單，逐一判斷技術訊號並自動下單"""
    symbols = payload.get("symbols", [])
    if not symbols:
        raise HTTPException(status_code=400, detail="Missing 'symbols'")

    service = request.app.state.trading_service

    async def _run():
        from src.strategies.volume_strategy import VolumeStrategy
        from src.strategies.crypto_strategy import CryptoStrategy
        from src.stock.fetcher import fetch_history
        from config import (
            TW_TRADE_AMOUNT, US_TRADE_AMOUNT, CRYPTO_TRADE_AMOUNT,
            TW_CONFIG, US_CONFIG, CRYPTO_CONFIG,
        )

        for sym in symbols:
            try:
                sym = str(sym).upper()
                if re.match(r"^\d+$", sym):
                    cfg, budget, market = TW_CONFIG, TW_TRADE_AMOUNT, "tw"
                    strategy = VolumeStrategy(cfg["MIN_VOLUME"], cfg["SPIKE_MULTIPLIER"], cfg["PRICE_UP_THRESHOLD"])
                elif "/" in sym or sym.endswith("USDT"):
                    cfg, budget, market = CRYPTO_CONFIG, CRYPTO_TRADE_AMOUNT, "crypto"
                    strategy = CryptoStrategy(cfg["MIN_VOLUME"], cfg["SPIKE_MULTIPLIER"], cfg["PRICE_UP_THRESHOLD"])
                else:
                    cfg, budget, market = US_CONFIG, US_TRADE_AMOUNT, "us"
                    strategy = VolumeStrategy(cfg["MIN_VOLUME"], cfg["SPIKE_MULTIPLIER"], cfg["PRICE_UP_THRESHOLD"])

                df = fetch_history(sym)
                if df is None:
                    continue
                passed, points = strategy.check_buy(df)
                if not passed or not points:
                    continue

                entry_price = points["entry_price"]
                if market == "tw":
                    raw_qty = budget / entry_price
                    qty = int(raw_qty // 1000 * 1000) if raw_qty >= 1000 else int(raw_qty)
                elif market == "crypto":
                    qty = round(budget / entry_price, 4)
                else:
                    qty = int(budget / entry_price)

                if qty <= 0:
                    continue

                await service.execute_smart_buy(
                    sym, qty,
                    custom_entry=entry_price,
                    custom_tp=points["take_profit"],
                )
            except Exception as e:
                logger.error(f"[Robot] 處理 {sym} 失敗: {e}")

    background_tasks.add_task(_run)
    return {"status": "robot_trading_initiated", "symbols": symbols}
