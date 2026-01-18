"""
应用配置
"""
import os
from dotenv import load_dotenv

load_dotenv()

# 输出目录
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "generated_diagrams")

# gRPC 服务器端口
GRPC_SERVER_PORT = os.getenv("SERVER_PORT", "9091")

# FastAPI 配置
API_TITLE = os.getenv("API_TITLE", "AI & Diagram Server")
API_DESCRIPTION = os.getenv("API_DESCRIPTION", "提供影像识别、架构图生成、职位图生成和爬虫功能的 Python 微服务")
API_VERSION = os.getenv("API_VERSION", "1.0.0")
