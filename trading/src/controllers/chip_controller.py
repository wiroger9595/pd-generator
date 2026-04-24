"""
籌碼面分析 Controller  —  /api/chip/*
"""
from fastapi import APIRouter, Query
from src.utils.logger import logger

router = APIRouter(prefix="/api/chip", tags=["Chip"])


@router.post("/buy/us")
async def chip_buy_us(top_n: int = Query(5), max_scan: int = Query(20)):
    from src.services.chip_service import get_us_chip_buy
    result = await get_us_chip_buy(top_n=top_n, max_scan=max_scan)
    logger.info(f"[Chip] 美股買進完成，推薦 {len(result.get('recommendations', []))} 檔")
    return result


@router.post("/sell/us")
async def chip_sell_us(max_scan: int = Query(20)):
    from src.services.chip_service import get_us_chip_sell
    result = await get_us_chip_sell(max_scan=max_scan)
    logger.info(f"[Chip] 美股賣出完成，訊號 {len(result.get('sell_signals', []))} 檔")
    return result


@router.post("/buy/tw")
async def chip_buy_tw(top_n: int = Query(5), max_scan: int = Query(30)):
    from src.services.chip_service import get_tw_chip_buy
    result = await get_tw_chip_buy(top_n=top_n, max_scan=max_scan)
    logger.info(f"[Chip] 台股買進完成，推薦 {len(result.get('recommendations', []))} 檔")
    return result


@router.post("/sell/tw")
async def chip_sell_tw(max_scan: int = Query(50)):
    from src.services.chip_service import get_tw_chip_sell
    result = await get_tw_chip_sell(max_scan=max_scan)
    logger.info(f"[Chip] 台股賣出完成，訊號 {len(result.get('sell_signals', []))} 檔")
    return result
