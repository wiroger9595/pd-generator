"""
Finnhub 每日掃描 watchlist
納入：記憶體/半導體核心 + AI 龍頭 + 主流大型股
免費 API 60 req/min，每檔 4 calls，建議池大小 50–80 檔
"""

# 記憶體 / 半導體 / AI 核心
SEMI_AI_CORE = [
    "MU", "SNDK", "TSM", "NVDA", "AVGO", "AMD", "SMCI", "ASML",
    "INTC", "QCOM", "MRVL", "TXN", "MCHP", "ADI", "ON", "LRCX",
    "AMAT", "KLAC", "ARM", "WDC",
]

# 軟體 / 雲端 / AI 應用
SOFTWARE_CLOUD = [
    "MSFT", "GOOGL", "META", "AMZN", "ORCL", "CRM", "PLTR",
    "NOW", "SNOW", "DDOG", "NET", "MDB", "CRWD",
]

# 大型市值 + 高動能
LARGE_CAP_MOMENTUM = [
    "AAPL", "TSLA", "NFLX", "COIN", "HOOD", "UBER", "ABNB",
    "SHOP", "SQ", "PYPL",
]

# 半導體設備 / 材料
SEMI_EQUIP = [
    "ENTG", "UCTT", "CDNS", "SNPS", "ANET", "MPWR",
]


def get_default_watchlist() -> list[str]:
    """預設掃描池，去重後回傳"""
    seen = set()
    out = []
    for group in (SEMI_AI_CORE, SOFTWARE_CLOUD, LARGE_CAP_MOMENTUM, SEMI_EQUIP):
        for t in group:
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out
