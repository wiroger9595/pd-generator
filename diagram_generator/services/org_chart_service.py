"""
职位图生成服务
"""
from typing import List
from collections import defaultdict
import graphviz

from diagram_generator.models.position import Position
from diagram_generator.utils.diagram_utils import check_graphviz_availability, get_node_label_html


class OrgChartService:
    """职位图生成服务类"""

    def generate_org_chart(self, positions: List[Position]) -> bytes:
        """
        根据职位列表生成组织架构图
        
        Args:
            positions: 职位列表
            
        Returns:
            PNG 格式的图片字节数据
        """
        # 检查 Graphviz 可用性
        try:
            check_graphviz_availability()
        except RuntimeError as e:
            raise RuntimeError(f"Graphviz 不可用: {e}")

        # 初始化有向图
        dot = graphviz.Digraph(
            comment='Organization Chart',
            format='png',
            graph_attr={
                'rankdir': 'TB',
                'splines': 'ortho',
                'nodesep': '0.5',
                'ranksep': '0.75'
            },
            node_attr={'shape': 'none'}
        )

        # 数据结构化与 ID 映射
        id_to_node_map: dict[str, dict] = {}
        level_nodes: dict[int, list[str]] = defaultdict(list)

        for pos in positions:
            # 员工 ID 作为 Graphviz 内部 ID
            node_id_gv = str(pos.employee_id)

            if node_id_gv == "0" or node_id_gv == "N/A" or not node_id_gv:
                print(f"警告: 发现无效或空的 employeeId，跳过该节点: {pos}")
                continue

            node_info = {
                "id": node_id_gv,
                "employeeId": node_id_gv,
                "parentId": pos.parent_id or "",
                "name": pos.name,
                "level": pos.level,
                "title": pos.title,
                "department": pos.department,
                "subDepartment": pos.sub_department or ""
            }

            id_to_node_map[node_info["employeeId"]] = node_info
            level_nodes[node_info["level"]].append(node_id_gv)

            # 生成节点标签
            label_html = get_node_label_html(node_info)
            dot.node(node_id_gv, label_html)

        # 产生边 (Edge) - 基于 ID 的向下关联
        for node_id_str, node in id_to_node_map.items():
            parent_id_str = node["parentId"]

            # 只有当 parent_id_str 存在且能在 id_to_node_map 中找到时才连接
            if parent_id_str and parent_id_str in id_to_node_map:
                dot.edge(parent_id_str, node_id_str)

        # Graphviz 强制分层 (确保上下级关系的视觉化)
        for level, node_ids in level_nodes.items():
            if level > 0:
                with dot.subgraph(name=f'cluster_level_{level}') as sub:
                    sub.attr(rank='same', style='invis')  # 强制同级节点水平对齐
                    for node_id in node_ids:
                        sub.node(node_id)

        # 生成 PNG
        image_data = dot.pipe()
        return image_data
