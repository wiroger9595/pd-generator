"""
自定义异常
"""
from fastapi import HTTPException


class DiagramGenerationError(HTTPException):
    """图表生成错误"""
    def __init__(self, detail: str):
        super().__init__(status_code=500, detail=f"生成图表失败: {detail}")


class OrgChartGenerationError(HTTPException):
    """职位图生成错误"""
    def __init__(self, detail: str):
        super().__init__(status_code=500, detail=f"生成职位图失败: {detail}")


class CrawlerError(HTTPException):
    """爬虫错误"""
    def __init__(self, detail: str):
        super().__init__(status_code=500, detail=f"爬虫执行失败: {detail}")
