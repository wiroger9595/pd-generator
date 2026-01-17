# 檔案路徑：app/main.py
# 這是 FastAPI 的核心定義檔

from fastapi import FastAPI
from diagram_generator.core.config import API_TITLE, API_DESCRIPTION, API_VERSION
from diagram_generator.api.routes import image, diagram, org_chart, crawler

# 1. 建立 FastAPI 實例
diagram_generator = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
)

# 2. 註冊路由
diagram_generator.include_router(image.router)
diagram_generator.include_router(diagram.router)
diagram_generator.include_router(org_chart.router)
diagram_generator.include_router(crawler.router)

# 3. 根路徑
@diagram_generator.get("/", summary="根路徑", include_in_schema=False)
async def root():
    return {
        "message": "Welcome to AI & Diagram Server!",
        "docs": "/docs",
        "version": API_VERSION
    }

@diagram_generator.get("/health", summary="健康檢查", tags=["Health"])
async def health_check():
    return {"status": "healthy", "version": API_VERSION}