"""
Gemini AI Repository
使用 google-generativeai (gemini-1.5-flash) 進行新聞情緒分析
免費方案：每分鐘 15 次，每日 1500 次請求
"""
import os
from src.utils.logger import logger

_INSTANCE = None

_SENTIMENT_PROMPT = """你是一位專業的股票分析師。以下是關於股票「{ticker}」（{name}）的最新新聞標題列表：

{news_text}

請根據這些新聞標題，分析對該股票的情緒影響，並以 JSON 格式回傳：
{{
  "sentiment": "positive" | "neutral" | "negative",
  "score": <整數，正面為正數，負面為負數，範圍 -100 到 100>,
  "summary": "<繁體中文一句話摘要，說明主要情緒因素>",
  "key_factors": ["<主要因素1>", "<主要因素2>"]
}}

只回傳 JSON，不要其他說明文字。"""


class GeminiRepository:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._model = genai.GenerativeModel("gemini-1.5-flash")
            except ImportError:
                logger.error("[Gemini] google-generativeai 未安裝，請執行 pip install google-generativeai")
                return None
            except Exception as e:
                logger.error(f"[Gemini] 初始化失敗: {e}")
                return None
        return self._model

    def analyze_sentiment(
        self,
        ticker: str,
        name: str,
        news_items: list[dict],
    ) -> dict:
        """
        分析新聞情緒
        news_items: [{"title": str, ...}, ...]
        回傳: {"sentiment", "score", "summary", "key_factors"}
        """
        if not news_items:
            return {"sentiment": "neutral", "score": 0, "summary": "無新聞可分析", "key_factors": []}

        model = self._get_model()
        if not model:
            return {"sentiment": "neutral", "score": 0, "summary": "Gemini 未初始化", "key_factors": []}

        # 只取標題（避免 token 超額）
        titles = [item["title"] for item in news_items if item.get("title")]
        if not titles:
            return {"sentiment": "neutral", "score": 0, "summary": "無有效標題", "key_factors": []}

        news_text = "\n".join(f"- {t}" for t in titles[:15])  # 最多 15 則
        prompt = _SENTIMENT_PROMPT.format(
            ticker=ticker, name=name or ticker, news_text=news_text
        )

        try:
            response = model.generate_content(prompt)
            raw = response.text.strip()

            # 清除可能的 markdown 代碼塊
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            import json
            result = json.loads(raw)
            logger.info(f"[Gemini] {ticker} 情緒: {result.get('sentiment')} score={result.get('score')}")
            return result
        except Exception as e:
            logger.error(f"[Gemini] 情緒分析失敗 {ticker}: {e}")
            return {"sentiment": "neutral", "score": 0, "summary": f"分析失敗: {e}", "key_factors": []}


def get_gemini_repo() -> GeminiRepository:
    global _INSTANCE
    if _INSTANCE is None:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            logger.warning("[Gemini] GEMINI_API_KEY 未設定")
        _INSTANCE = GeminiRepository(api_key)
    return _INSTANCE
