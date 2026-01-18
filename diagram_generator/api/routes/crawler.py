"""
爬虫路由（预留）
后续添加爬虫功能时使用
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from crawler.core.scheduler import job as run_crawler_job

from diagram_generator.models.crawler import CrawlerConfig, CrawlerResult
from diagram_generator.services.crawler_service import CrawlerService
from diagram_generator.core.exceptions import CrawlerError

router = APIRouter(prefix="/crawler", tags=["Crawler"])

# 创建服务实例
crawler_service = CrawlerService()


@router.post("/crawl", summary="执行爬虫任务", response_model=CrawlerResult)
async def crawl(config: CrawlerConfig):
    """
    执行爬虫任务（预留接口）
    
    **注意**: 此功能尚未实现，当前返回占位响应。
    """
    try:
        result = await crawler_service.crawl(config)
        return result
    except Exception as e:
        raise CrawlerError(str(e))


@router.post("/crawl_jobs", summary="爬取职位信息")
async def crawl_job_positions(url: str):
    """
    爬取职位信息（预留接口）
    
    **注意**: 此功能尚未实现，当前返回空列表。
    """
    try:
        positions = await crawler_service.crawl_job_positions(url)
        return {"positions": positions, "count": len(positions)}
    except Exception as e:
        raise CrawlerError(str(e))


@router.post("/trigger", summary="手動觸發爬蟲 (背景執行)")
async def trigger_crawler(background_tasks: BackgroundTasks):
    """
    手動觸發後端爬蟲任務。
    爬蟲將在背景執行，不會阻塞 API 回應。
    """
    try:
        background_tasks.add_task(run_crawler_job)
        return {"status": "accepted", "message": "Crawler job started in background"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
