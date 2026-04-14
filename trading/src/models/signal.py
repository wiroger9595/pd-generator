from typing import TypedDict


class ScoreResult(TypedDict):
    """單一面向對一支股票的評分結果"""
    ticker: str
    name: str
    score: int
    reason: str


class AnalysisResult(TypedDict):
    """彙整多個 ScoreResult 後的輸出格式"""
    status: str
    market: str
    scanned: int
    matched: int
    recommendations: list  # list[ScoreResult]
