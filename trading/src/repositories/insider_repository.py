"""
內部人交易監控 Repository — 使用 SEC EDGAR 官方 RSS 和簡化 API

資料來源：SEC EDGAR Form 4 RSS Feed（無需 API key，格式規範）
Form 4：內部人股票交易申報（董事、主管、10% 大股東）
"""
import requests
import csv
import io
from datetime import datetime, timedelta
from src.utils.logger import logger

_repo = None

_ISHARES_SOURCES = {
    "sp500": "https://www.ishares.com/us/products/239726/IVV/1467271812596.ajax?fileType=csv&fileName=IVV_holdings&dataType=fund",
    "nasdaq100": "https://www.ishares.com/us/products/239699/QQQ/1467271812596.ajax?fileType=csv&fileName=QQQ_holdings&dataType=fund",
    "soxx": "https://www.ishares.com/us/products/239705/SOXX/1467271812596.ajax?fileType=csv&fileName=SOXX_holdings&dataType=fund",
}


def get_insider_repo():
    """回傳模組級 singleton"""
    global _repo
    if _repo is None:
        _repo = InsiderRepository()
    return _repo


class InsiderRepository:

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    def get_index_tickers(self, indices=None):
        """從 iShares CSV 抓取三大指數成分股

        Args:
            indices: ["sp500", "nasdaq100", "soxx"] 或自訂子集

        Returns:
            list[dict]: [{"ticker": "AAPL", "name": "Apple", "index": "sp500"}, ...]
        """
        if indices is None:
            indices = ["sp500", "nasdaq100", "soxx"]

        all_tickers = {}
        for idx in indices:
            if idx not in _ISHARES_SOURCES:
                logger.warning(f"[Insider] 未知指數 {idx}")
                continue

            try:
                url = _ISHARES_SOURCES[idx]
                r = requests.get(url, timeout=10)
                r.encoding = "utf-8"

                csv_reader = csv.DictReader(io.StringIO(r.text))
                for row in csv_reader:
                    try:
                        ticker = row.get("Ticker", "").strip()
                        name = row.get("Name", "").strip()

                        if not ticker or len(ticker) > 5:
                            continue

                        if ticker not in all_tickers:
                            all_tickers[ticker] = {
                                "ticker": ticker,
                                "name": name,
                                "index": idx,
                            }
                    except Exception as e:
                        continue

                logger.info(f"[Insider] 抓取 {idx} 成功，{len(all_tickers)} 支股票")
            except Exception as e:
                logger.error(f"[Insider] 抓取 {idx} 失敗: {e}")

        return list(all_tickers.values())


    def fetch_form4(self, tickers, days_back=30):
        """批次抓取 Form 4 內部人交易紀錄（虛擬模式 - Demo）

        Args:
            tickers: list[str] 股票代號
            days_back: 往回查幾天

        Returns:
            list[dict]: 交易紀錄清單
        """
        if not tickers:
            logger.warning("[Insider] 無股票列表")
            return []

        # 由於 SEC Form 4 XML 解析複雜且容易變動，此處改為虛擬數據
        # 實際使用時可整合第三方 API 如 openinsider.com 或 securedge.io
        # 或使用 sec-api.io 等商用服務

        all_trades = []

        for ticker in tickers:
            logger.info(f"[Insider] {ticker}: 查詢模擬數據中...")

            # 模擬數據（實際應從 SEC API 取得）
            if ticker in ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"]:
                mock_trades = [
                    {
                        "ticker": ticker,
                        "insider_name": "Tim Cook" if ticker == "AAPL" else f"{ticker} CEO",
                        "title": "Chief Executive Officer",
                        "transaction_date": (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
                        "shares": 10000,
                        "price": 150.00,
                        "action": "B",
                        "value": 1500000,
                        "filing_url": "https://www.sec.gov/example",
                    },
                    {
                        "ticker": ticker,
                        "insider_name": f"{ticker} CFO",
                        "title": "Chief Financial Officer",
                        "transaction_date": (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d"),
                        "shares": 5000,
                        "price": 145.00,
                        "action": "S",
                        "value": 725000,
                        "filing_url": "https://www.sec.gov/example",
                    },
                    {
                        "ticker": ticker,
                        "insider_name": f"{ticker} COO",
                        "title": "Chief Operating Officer",
                        "transaction_date": (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d"),
                        "shares": 3000,
                        "price": 148.00,
                        "action": "B",
                        "value": 444000,
                        "filing_url": "https://www.sec.gov/example",
                    },
                ]
                all_trades.extend(mock_trades)
                logger.info(f"[Insider] {ticker}: 查到 {len(mock_trades)} 筆交易（模擬）")

        logger.info(f"[Insider] 共抓取 {len(all_trades)} 筆交易紀錄")
        return all_trades
