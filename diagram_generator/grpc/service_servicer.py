"""
gRPC 服务实现
使用新的服务层
"""
import grpc
from typing import List

import proto.TreeDiagramGenerateGrpc_pb2 as pb2
import proto.TreeDiagramGenerateGrpc_pb2_grpc as pb2_grpc

from diagram_generator.services.org_chart_service import OrgChartService
from diagram_generator.models.position import Position


class TreeDiagramServiceServicer(pb2_grpc.TreeDiagramGenerateGrpcServiceServicer):
    """
    实现 gRPC 服务，处理职位数据并生成阶层图。
    使用新的 OrgChartService 服务层。
    """

    def __init__(self):
        """初始化服务"""
        self.org_chart_service = OrgChartService()

    def getImage(self, request, context):
        """
        接收请求，绘制图表，并以 bytes 回传。
        """
        print("接收到 getImage 请求：")

        # 将 gRPC repeated field 转换为 Python list
        positions_data = list(request.position)

        # 打印接收到的数据（调试用）
        for position in positions_data:
            print(f"  level: {position.level}, title: {position.title}, employeeId: {position.employeeId}")

        try:
            # 将 gRPC Position 转换为 Pydantic Position 模型
            positions = self._convert_grpc_to_pydantic(positions_data)

            # 使用服务层生成职位图
            image_data = self.org_chart_service.generate_org_chart(positions)

        except Exception as e:
            # 捕获所有绘图错误
            import traceback
            traceback.print_exc()
            context.set_details(f"绘图失败: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            return pb2.TreeDiagramGenerateGrpcResponse()

        print(f"成功绘制 {len(positions_data)} 个职位的阶层图，大小为 {len(image_data)} bytes。")

        return pb2.TreeDiagramGenerateGrpcResponse(treeDiagramData=image_data)

    def saveProjectWithImage(self, request, context):
        """
        保存项目并返回图片数据
        目前直接返回图片数据
        """
        return self.getImage(request, context)

    def _convert_grpc_to_pydantic(self, grpc_positions: List[pb2.Position]) -> List[Position]:
        """
        将 gRPC Position 消息转换为 Pydantic Position 模型
        
        Args:
            grpc_positions: gRPC Position 消息列表
            
        Returns:
            Pydantic Position 模型列表
        """
        positions = []
        for grpc_pos in grpc_positions:
            # 安全地获取 gRPC 消息字段
            position = Position(
                level=getattr(grpc_pos, 'level', 0),
                employee_id=str(getattr(grpc_pos, 'employeeId', '')),
                parent_id=str(getattr(grpc_pos, 'parentId', '')) if getattr(grpc_pos, 'parentId', '') else None,
                name=str(getattr(grpc_pos, 'name', '')),
                title=str(getattr(grpc_pos, 'title', '')),
                department=str(getattr(grpc_pos, 'department', '')),
                sub_department=str(getattr(grpc_pos, 'subDepartment', '')) if getattr(grpc_pos, 'subDepartment', '') else None
            )
            positions.append(position)
        return positions
