"""
架构图配置模型
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal


class NodeConfig(BaseModel):
    """节点配置"""
    id: str = Field(..., description="节点唯一标识")
    label: str = Field(..., description="节点显示标签")
    type: str = Field(default="Node", description="节点类型（EC2, S3, RDS, Node等）")


class EdgeConfig(BaseModel):
    """边（连接）配置"""
    source: str = Field(..., description="源节点ID")
    target: str = Field(..., description="目标节点ID")
    label: Optional[str] = Field(None, description="连接标签")


class DiagramConfig(BaseModel):
    """架构图配置"""
    name: str = Field(..., description="图表名称")
    nodes: list[NodeConfig] = Field(..., description="节点列表")
    edges: list[EdgeConfig] = Field(default_factory=list, description="边（连接）列表")
    direction: Literal["LR", "TB", "BT", "RL"] = Field(default="LR", description="图表方向")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "My_AWS_Architecture",
                "nodes": [
                    {"id": "ec2_app", "label": "Web App", "type": "EC2"},
                    {"id": "s3_storage", "label": "Static Files", "type": "S3"},
                    {"id": "rds_db", "label": "Database", "type": "RDS"}
                ],
                "edges": [
                    {"source": "ec2_app", "target": "s3_storage", "label": "读取/写入"},
                    {"source": "ec2_app", "target": "rds_db", "label": "查询"}
                ],
                "direction": "LR"
            }
        }
