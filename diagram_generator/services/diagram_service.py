"""
通用架构图生成服务
"""
import os
from diagrams import Diagram, Node, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.storage import S3
from diagrams.aws.database import RDS

from diagram_generator.models.diagram import DiagramConfig


class DiagramService:
    """架构图生成服务类"""

    def __init__(self, output_dir: str = "generated_diagrams"):
        """
        初始化服务
        
        Args:
            output_dir: 输出目录
        """
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        # 节点类型映射
        self.node_type_map = {
            "EC2": EC2,
            "S3": S3,
            "RDS": RDS,
            "Node": Node
        }

    def generate_diagram(self, config: DiagramConfig) -> bytes:
        """
        根据配置生成架构图
        
        Args:
            config: 图表配置
            
        Returns:
            PNG 格式的图片字节数据
        """
        # 清理图表名称，只保留字母、数字和下划线
        sanitized_name = "".join(c for c in config.name if c.isalnum() or c == "_")
        output_filename = os.path.join(self.output_dir, sanitized_name)

        try:
            with Diagram(
                name=config.name,
                show=False,
                filename=output_filename,
                direction=config.direction
            ) as diag:
                diagram_nodes = {}

                # 创建节点
                for node_cfg in config.nodes:
                    node_class = self.node_type_map.get(node_cfg.type, Node)
                    diagram_nodes[node_cfg.id] = node_class(node_cfg.label)

                # 创建边（连接）
                for edge_cfg in config.edges:
                    source_node = diagram_nodes.get(edge_cfg.source)
                    target_node = diagram_nodes.get(edge_cfg.target)

                    if source_node and target_node:
                        if edge_cfg.label:
                            source_node >> Edge(label=edge_cfg.label) >> target_node
                        else:
                            source_node >> target_node
                    else:
                        print(f"警告: 找不到节点 '{edge_cfg.source}' 或 '{edge_cfg.target}'")

            # Diagrams 默认会生成 .png 文件
            image_path = f"{output_filename}.png"

            # 读取生成的图片
            with open(image_path, "rb") as f:
                image_bytes = f.read()

            return image_bytes

        except Exception as e:
            raise RuntimeError(f"生成图表失败: {str(e)}")
