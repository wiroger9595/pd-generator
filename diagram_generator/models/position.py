"""
职位数据模型
基于 gRPC proto 定义的 Position 结构
"""
from pydantic import BaseModel, Field
from typing import Optional


class Position(BaseModel):
    """职位数据模型"""
    level: int = Field(..., description="层级，从1开始")
    employee_id: str = Field(..., alias="employeeId", description="员工ID")
    parent_id: Optional[str] = Field(None, alias="parentId", description="上级员工ID")
    name: str = Field(..., description="员工姓名")
    title: str = Field(..., description="职位名称")
    department: str = Field(..., description="部门名称")
    sub_department: Optional[str] = Field(None, alias="subDepartment", description="子部门名称")

    class Config:
        populate_by_name = True  # 允许使用字段名或别名
        json_schema_extra = {
            "example": {
                "level": 1,
                "employee_id": "001",
                "parent_id": None,
                "name": "张三",
                "title": "CEO",
                "department": "管理部",
                "sub_department": None
            }
        }


class OrgChartRequest(BaseModel):
    """职位图生成请求模型"""
    positions: list[Position] = Field(..., description="职位列表")

    class Config:
        json_schema_extra = {
            "example": {
                "positions": [
                    {
                        "level": 1,
                        "employee_id": "001",
                        "parent_id": None,
                        "name": "张三",
                        "title": "CEO",
                        "department": "管理部",
                        "sub_department": None
                    },
                    {
                        "level": 2,
                        "employee_id": "002",
                        "parent_id": "001",
                        "name": "李四",
                        "title": "技术总监",
                        "department": "技术部",
                        "sub_department": None
                    }
                ]
            }
        }
