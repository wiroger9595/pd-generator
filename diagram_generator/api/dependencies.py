"""
依赖注入
"""
from diagram_generator.services.org_chart_service import OrgChartService
from diagram_generator.services.diagram_service import DiagramService
from diagram_generator.services.crawler_service import CrawlerService
from diagram_generator.core.config import OUTPUT_DIR


def get_org_chart_service() -> OrgChartService:
    """获取职位图服务实例"""
    return OrgChartService()


def get_diagram_service() -> DiagramService:
    """获取架构图服务实例"""
    return DiagramService(output_dir=OUTPUT_DIR)


def get_crawler_service() -> CrawlerService:
    """获取爬虫服务实例"""
    return CrawlerService()
