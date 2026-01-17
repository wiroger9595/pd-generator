"""
职位图生成路由
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from diagram_generator.models.position import OrgChartRequest
from diagram_generator.services.org_chart_service import OrgChartService
from diagram_generator.core.exceptions import OrgChartGenerationError

router = APIRouter(prefix="/org_chart", tags=["Organization Chart"])

# 创建服务实例
org_chart_service = OrgChartService()


@router.post("/generate", summary="生成职位图")
async def generate_org_chart(request: OrgChartRequest):
    """
    根据提供的职位列表生成组织架构图。
    
    **示例请求 body:**
    ```json
    {
        "positions": [
            {
                "level": 1,
                "employeeId": "001",
                "parentId": null,
                "name": "张三",
                "title": "CEO",
                "department": "管理部",
                "subDepartment": null
            },
            {
                "level": 2,
                "employeeId": "002",
                "parentId": "001",
                "name": "李四",
                "title": "技术总监",
                "department": "技术部",
                "subDepartment": null
            }
        ]
    }
    ```
    """
    try:
        image_bytes = org_chart_service.generate_org_chart(request.positions)
        return Response(content=image_bytes, media_type="image/png")
    except Exception as e:
        raise OrgChartGenerationError(str(e))
