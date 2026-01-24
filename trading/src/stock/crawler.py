import requests
import pandas as pd
from io import StringIO  # <--- 新增這個來解決 FutureWarning

from src.utils.logger import logger

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
            res = requests.get(target['url'])
            
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
    從 BlackRock (iShares) 抓取 S&P 500 (IVV) 持股清單
    這是世界最大的資產管理公司提供的官方持股資料，比 Wikipedia 更專業且精確。
    """
    logger.info("📥 正在從 BlackRock 抓取 S&P 500 (IVV) 持股清單...")
    try:
        url = "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/1467271812596.ajax?fileType=csv&fileName=IVV_holdings&dataType=fund"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers)
        res.encoding = 'utf-8-sig'
        lines = res.text.splitlines()
        header_index = 0
        for i, line in enumerate(lines):
            if line.startswith("Ticker"):
                header_index = i
                break
        df = pd.read_csv(StringIO("\n".join(lines[header_index:])))
        df = df[df['Asset Class'] == 'Equity']
        df = df.dropna(subset=['Ticker'])
        result = []
        for _, row in df.iterrows():
            ticker = str(row['Ticker']).strip().replace('.', '-')
            result.append({'ticker': ticker, 'name': row['Name']})
        logger.info(f"✅ 美股清單取得: {len(result)} 檔 (來源: BlackRock iShares)")
        return result
    except Exception as e:
        logger.error(f"❌ 抓取 BlackRock 美股清單失敗: {e}")
        return []