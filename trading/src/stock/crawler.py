import os
import datetime
import requests
import urllib3
import pandas as pd
from io import StringIO

from src.utils.logger import logger

# isin.twse.com.tw 憑證缺少 Subject Key Identifier，停用該 host 的 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ── 全市場動能預篩 ──────────────────────────────────────────────────────────

def get_us_market_movers(top_n: int = 80) -> list[dict]:
    """
    用 Polygon grouped daily bars 取得全美股昨日表現。
    以 |change%| × volume 排序，回傳動能最強的 top_n 檔（漲跌皆包含）。

    門檻：收盤價 ≥ $5、成交量 ≥ 100 萬股（過濾仙股與低流動性）
    資料來源：Polygon /v2/aggs/grouped — 免費方案支援，約 15 分鐘延遲。
    """
    api_key = os.getenv("POLYGON_API_KEY", "")
    if not api_key:
        logger.warning("[MarketMovers] 無 POLYGON_API_KEY，跳過全市場預篩")
        return []

    # 往前最多找 5 個交易日（跳過週末 / 假日）
    for days_back in range(1, 6):
        date = (datetime.date.today() - datetime.timedelta(days=days_back)).strftime("%Y-%m-%d")
        try:
            url = (
                f"https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{date}"
                f"?adjusted=true&apiKey={api_key}"
            )
            resp = requests.get(url, timeout=30)
            data = resp.json()
            results = data.get("results", [])
            if results:
                logger.info(f"[MarketMovers] Polygon grouped daily {date}: {len(results)} 檔")
                break
        except Exception as e:
            logger.debug(f"[MarketMovers] Polygon {date} 失敗: {e}")
            results = []
    else:
        return []

    scored = []
    for r in results:
        o = r.get("o", 0)
        c = r.get("c", 0)
        v = r.get("v", 0)
        ticker = r.get("T", "")
        if not ticker or o <= 0 or c < 5 or v < 1_000_000:
            continue
        change_pct = (c - o) / o
        momentum = abs(change_pct) * v   # 方向不限，漲跌都可能是機會
        scored.append({
            "ticker": ticker,
            "name":   ticker,
            "change_pct": round(change_pct, 4),
            "volume":     int(v),
            "_momentum":  momentum,
        })

    scored.sort(key=lambda x: x["_momentum"], reverse=True)
    top = [{"ticker": s["ticker"], "name": s["name"]} for s in scored[:top_n]]
    logger.info(f"[MarketMovers] US 預篩完成: 取前 {len(top)} 檔高動能標的")
    return top


def get_tw_market_movers(top_n: int = 80) -> list[dict]:
    """
    用 TWSE + TPEX OpenAPI 取得最新一日全台股收盤資料。
    以 |change%| × 成交量 排序，回傳動能最強的 top_n 檔。

    資料來源：
      上市：https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL
      上櫃：https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes
    皆為公開免費 API，無需 API Key。
    """
    stocks = []

    # ── 上市 (TWSE) ──────────────────────────────────────────────────────
    try:
        resp = requests.get(
            "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
            timeout=15,
        )
        for row in resp.json():
            code = str(row.get("Code", "")).strip()
            if not (len(code) == 4 and code.isdigit()):
                continue
            try:
                close    = float(str(row.get("ClosingPrice",  "0")).replace(",", "") or 0)
                open_p   = float(str(row.get("OpeningPrice",  "0")).replace(",", "") or 0)
                volume   = float(str(row.get("TradeVolume",   "0")).replace(",", "") or 0)
            except ValueError:
                continue
            if close < 10 or volume < 100_000:
                continue
            change_pct = (close - open_p) / open_p if open_p > 0 else 0
            stocks.append({
                "ticker":    f"{code}.TW",
                "name":      row.get("Name", code),
                "change_pct": round(change_pct, 4),
                "volume":     int(volume),
                "_momentum":  abs(change_pct) * volume,
            })
        logger.info(f"[MarketMovers] TWSE: {len(stocks)} 檔")
    except Exception as e:
        logger.warning(f"[MarketMovers] TWSE OpenAPI 失敗: {e}")

    # ── 上櫃 (TPEX) ──────────────────────────────────────────────────────
    tpex_count = 0
    try:
        resp = requests.get(
            "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
            timeout=15,
        )
        for row in resp.json():
            code = str(row.get("SecuritiesCompanyCode", "")).strip()
            if not (len(code) == 4 and code.isdigit()):
                continue
            try:
                close  = float(str(row.get("Close",         "0")).replace(",", "") or 0)
                open_p = float(str(row.get("Open",          "0")).replace(",", "") or 0)
                volume = float(str(row.get("TradingShares", "0")).replace(",", "") or 0) / 1000
            except ValueError:
                continue
            if close < 10 or volume < 100_000:
                continue
            change_pct = (close - open_p) / open_p if open_p > 0 else 0
            stocks.append({
                "ticker":     f"{code}.TWO",
                "name":       row.get("CompanyName", code),
                "change_pct": round(change_pct, 4),
                "volume":     int(volume),
                "_momentum":  abs(change_pct) * volume,
            })
            tpex_count += 1
        logger.info(f"[MarketMovers] TPEX: {tpex_count} 檔")
    except Exception as e:
        logger.warning(f"[MarketMovers] TPEX OpenAPI 失敗: {e}")

    if not stocks:
        return []

    stocks.sort(key=lambda x: x["_momentum"], reverse=True)
    top = [{"ticker": s["ticker"], "name": s["name"]} for s in stocks[:top_n]]
    logger.info(f"[MarketMovers] TW 預篩完成: 取前 {len(top)} 檔高動能標的")
    return top

def get_tw_stock_list():
    """
    抓取台股清單 (上市+上櫃)，使用更穩健的解析方式
    """
    logger.info("📥 正在抓取台股清單...")
    stocks = []

    # 定義要抓取的網址與對應後綴
    # mode=2: 上市, mode=4: 上櫃
    targets = [
        {"url": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", "suffix": ".TW", "type": "上市"},
        {"url": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4", "suffix": ".TWO", "type": "上櫃"}
    ]

    for target in targets:
        try:
            logger.info(f"   - 正在抓取{target['type']}股票...")
            res = requests.get(target['url'], verify=False, timeout=15)
            
            # 修正 FutureWarning: 使用 StringIO 包裝 HTML 字串
            df = pd.read_html(StringIO(res.text))[0]
            
            # 設定第 0 列為 Header
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            
            # 取得第一欄的資料
            col_data = df.iloc[:, 0] 
            
            for item in col_data:
                item = str(item)
                parts = item.split()
                
                if len(parts) >= 2:
                    code = parts[0]
                    name = parts[1]
                    
                    if len(code) == 4 and code.isdigit():
                        stocks.append({
                            'ticker': f"{code}{target['suffix']}",
                            'name': name
                        })
                        
        except Exception as e:
            logger.error(f"❌ 抓取{target['type']}清單時發生錯誤: {e}")
            continue

    if stocks:
        logger.info(f"✅ 台股清單取得成功: 共 {len(stocks)} 檔")
    else:
        logger.error("❌ 台股清單抓取失敗，結果為空")
        
    return stocks

def get_us_stock_list():
    """
    綜合抓取美股多個關鍵增長指數持股：
    1. S&P 500 (IVV)
    2. NASDAQ 100 (IWM - 替代為科技成長標幹)
    3. Russell 2000 Growth (IWO)
    4. S&P MidCap 400 Growth (IJK)
    5. ARK Innovation (ARKK)
    """
    all_stocks = {} # 使用 dict 去重: ticker -> name
    
    # 1. iShares 系列 (S&P 500, Russell Growth, MidCap Growth)
    ishares_targets = [
        {"name": "S&P 500", "url": "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/1467271812596.ajax?fileType=csv&fileName=IVV_holdings&dataType=fund"},
        {"name": "Russell 2000 Growth", "url": "https://www.ishares.com/us/products/239708/ishares-russell-2000-growth-etf/1467271812596.ajax?fileType=csv&fileName=IWO_holdings&dataType=fund"},
        {"name": "S&P MidCap 400 Growth", "url": "https://www.ishares.com/us/products/239764/ishares-sp-midcap-400-growth-etf/1467271812596.ajax?fileType=csv&fileName=IJK_holdings&dataType=fund"}
    ]

    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for target in ishares_targets:
        try:
            logger.info(f"📥 正在抓取 {target['name']} 持股...")
            res = requests.get(target['url'], headers=headers)
            res.encoding = 'utf-8-sig'
            lines = res.text.splitlines()
            header_index = -1
            for i, line in enumerate(lines):
                if line.startswith("Ticker"):
                    header_index = i
                    break
            if header_index == -1: continue
            
            df = pd.read_csv(StringIO("\n".join(lines[header_index:])))
            df = df[df['Asset Class'] == 'Equity']
            for _, row in df.iterrows():
                ticker = str(row['Ticker']).strip().replace('.', '-')
                if ticker and len(ticker) <= 5:
                    all_stocks[ticker] = row['Name']
        except Exception as e:
            logger.error(f"❌ 抓取 {target['name']} 失敗: {e}")

    # 2. ARK 系列 (ARKK)
    try:
        logger.info("📥 正在抓取 ARK Innovation (ARKK) 持股...")
        ark_url = "https://ark-funds.com/wp-content/uploads/funds-etf-csv/ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv"
        res = requests.get(ark_url, headers=headers)
        
        # ARK CSV 有時前幾行是 metadata (例如日期)，需要找到包含 'ticker' 的那一列作為 header
        lines = res.text.splitlines()
        data_start = -1
        for i, line in enumerate(lines):
            if 'ticker' in line.lower() and 'company' in line.lower():
                data_start = i
                break
        
        if data_start != -1:
            # 傳入 on_bad_lines='skip' 處理 ARK 特有的尾部變動
            df = pd.read_csv(StringIO("\n".join(lines[data_start:])), on_bad_lines='skip')
            if 'ticker' in df.columns:
                for _, row in df.iterrows():
                    ticker = str(row['ticker']).strip().upper()
                    # 排除 NaN, CASH 以及過長的垃圾字串
                    if ticker and ticker not in ['NAN', 'CASH'] and len(ticker) < 10:
                        all_stocks[ticker] = row.get('company', ticker)
        else:
            # Fallback
            df = pd.read_csv(StringIO(res.text), on_bad_lines='skip')
            if 'ticker' in df.columns:
                for _, row in df.iterrows():
                    ticker = str(row['ticker']).strip().upper()
                    if ticker and ticker != 'NAN' and ticker != 'CASH':
                        all_stocks[ticker] = row.get('company', ticker)

    except Exception as e:
        logger.error(f"❌ 抓取 ARK 清單失敗: {e}")

    # 轉回 List 格式
    result = [{"ticker": t, "name": n} for t, n in all_stocks.items()]
    logger.info(f"✅ 美股清單綜合取得成功: 共 {len(result)} 檔關鍵成長標的")
    return result

def get_crypto_stock_list():
    """
    抓取區塊鏈 (Crypto) 熱門交易對清單
    從 Binance 抓取前 50 檔成交量最大的 USDT 交易對
    """
    logger.info("📥 正在抓取區塊鏈熱門清單 (Binance)...")
    try:
        import ccxt
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        
        # 過濾 USDT 交易對並排序
        usdt_pairs = []
        for symbol, data in tickers.items():
            if symbol.endswith('/USDT'):
                usdt_pairs.append({
                    'ticker': symbol,
                    'name': symbol.split('/')[0],
                    'volume': data.get('quoteVolume', 0)
                })
        
        # 依成交量排序並取前 50
        usdt_pairs.sort(key=lambda x: x['volume'], reverse=True)
        top_50 = usdt_pairs[:50]
        
        logger.info(f"✅ 區塊鏈清單取得成功: 共 {len(top_50)} 檔熱門標的")
        return top_50
    except Exception as e:
        logger.error(f"❌ 抓取區塊鏈清單失敗: {e}")
        return [{"ticker": "BTC/USDT", "name": "BTC"}, {"ticker": "ETH/USDT", "name": "ETH"}]