"""
架构图生成路由
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from diagram_generator.models.diagram import DiagramConfig
from diagram_generator.services.diagram_service import DiagramService
from diagram_generator.core.config import OUTPUT_DIR
from diagram_generator.core.exceptions import DiagramGenerationError

router = APIRouter(prefix="/generate_diagram", tags=["Diagram Generation"])

# 创建服务实例
diagram_service = DiagramService(output_dir=OUTPUT_DIR)


@router.post("/", summary="生成架构图")
async def generate_diagram(config: DiagramConfig):
    """
    根据提供的 JSON 配置生成 Diagrams 架构图。
    配置应包含图表名称和节点/边缘的定义。
    """
    try:
        image_bytes = diagram_service.generate_diagram(config)
        return Response(content=image_bytes, media_type="image/png")
    except Exception as e:
        raise DiagramGenerationError(str(e))
