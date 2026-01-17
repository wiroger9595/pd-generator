"""
图表工具函数
"""
import graphviz
from typing import Dict, Any, List


def check_graphviz_availability():
    """检查 Graphviz 系统工具是否可用"""
    try:
        graphviz.Digraph().pipe()
    except Exception as e:
        raise RuntimeError(
            f"Graphviz 不可用。请确保已安装 Graphviz 系统工具。"
            f"安装方法: macOS: brew install graphviz, Ubuntu: sudo apt-get install graphviz"
            f"错误详情: {e}"
        )


def get_node_label_html(node_info: Dict[str, Any]) -> str:
    """
    生成 HTML 格式的节点标签
    用于在 Graphviz 中显示更丰富的节点信息
    """
    name = node_info.get("name", "N/A")
    title = node_info.get("title", "N/A")
    department = node_info.get("department", "")
    sub_department = node_info.get("subDepartment", "")
    level = node_info.get("level", 0)
    employee_id = node_info.get("employeeId", "")
    parent_id = node_info.get("parentId", "")

    # 构建显示文本
    dept_text = f"{department}"
    if sub_department:
        dept_text += f" / {sub_department}"

    html_label = f'''<
    <TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="4">
        <TR><TD COLSPAN="2" BGCOLOR="lightblue"><B>{name}</B></TD></TR>
        <TR><TD COLSPAN="2">{title}</TD></TR>
        <TR><TD COLSPAN="2">{dept_text}</TD></TR>
        <TR><TD>Level: {level}</TD><TD>ID: {employee_id}</TD></TR>
        <TR><TD COLSPAN="2" ALIGN="LEFT" STYLE="font-size:8px">Parent: {parent_id or 'ROOT'}</TD></TR>
    </TABLE>>'''
    return html_label
