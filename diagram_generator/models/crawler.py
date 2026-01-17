"""
爬虫数据模型（预留）
后续添加爬虫功能时使用
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class CrawlerConfig(BaseModel):
    """爬虫配置模型"""
    url: str = Field(..., description="目标URL")
    selector: Optional[str] = Field(None, description="CSS选择器")
    headers: Optional[Dict[str, str]] = Field(default_factory=dict, description="请求头")
    timeout: int = Field(default=30, description="超时时间（秒）")
    
    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://example.com/jobs",
                "selector": ".job-list",
                "headers": {"User-Agent": "Mozilla/5.0"},
                "timeout": 30
            }
        }


class CrawlerResult(BaseModel):
    """爬虫结果模型"""
    url: str = Field(..., description="爬取的URL")
    data: Dict[str, Any] = Field(..., description="爬取的数据")
    timestamp: datetime = Field(default_factory=datetime.now, description="爬取时间")
    success: bool = Field(..., description="是否成功")
    error: Optional[str] = Field(None, description="错误信息（如果有）")
