# 项目结构说明

## ✅ 重构完成

项目已成功重构为模块化架构，便于后续添加爬虫功能。

## 📁 目录结构

```
python-server-cmp/
├── app/                          # 主应用模块
│   ├── __init__.py
│   ├── main.py                   # FastAPI 应用入口
│   │
│   ├── api/                      # API 路由层
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── image.py          # 影像识别路由
│   │   │   ├── diagram.py        # 架构图路由
│   │   │   ├── org_chart.py      # 职位图路由 ⭐ 新增
│   │   │   └── crawler.py         # 爬虫路由（预留）🔮
│   │   └── dependencies.py        # 依赖注入
│   │
│   ├── models/                    # 数据模型层
│   │   ├── __init__.py
│   │   ├── position.py           # 职位数据模型 ⭐
│   │   ├── diagram.py            # 图表配置模型
│   │   └── crawler.py             # 爬虫数据模型（预留）🔮
│   │
│   ├── services/                 # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── org_chart_service.py  # 职位图服务 ⭐
│   │   ├── diagram_service.py    # 架构图服务
│   │   └── crawler_service.py     # 爬虫服务（预留接口）🔮
│   │
│   ├── core/                     # 核心配置
│   │   ├── __init__.py
│   │   ├── config.py            # 配置管理
│   │   └── exceptions.py        # 自定义异常
│   │
│   ├── utils/                    # 工具函数
│   │   ├── __init__.py
│   │   └── diagram_utils.py     # 图表工具函数
│   │
│   └── grpc/                     # gRPC 服务
│       ├── __init__.py
│       ├── service_servicer.py  # gRPC 服务实现（使用新服务层）⭐
│       └── server.py             # gRPC 服务器启动
│
├── proto/                        # gRPC proto 文件
├── main.py                       # 兼容性入口
├── server.py                     # gRPC 服务器（已更新）
└── README_REFACTOR.md            # 详细重构说明
```

## 🎯 核心功能

### 1. 职位图生成 ⭐ 新增功能

**FastAPI 端点**: `POST /org_chart/generate`

**请求示例**:
```json
{
  "positions": [
    {
      "level": 1,
      "employee_id": "001",
      "parent_id": null,
      "name": "张三",
      "title": "CEO",
      "department": "管理部",
      "sub_department": null
    },
    {
      "level": 2,
      "employee_id": "002",
      "parent_id": "001",
      "name": "李四",
      "title": "技术总监",
      "department": "技术部",
      "sub_department": null
    }
  ]
}
```

**gRPC 服务**: 继续支持，已更新使用新的服务层

### 2. 架构图生成

**端点**: `POST /generate_diagram/`

功能保持不变，代码已重构到服务层

### 3. 影像识别

**端点**: `POST /recognize_image/`

功能保持不变，代码已重构到路由层

### 4. 爬虫功能 🔮 预留接口

**端点**: 
- `POST /crawler/crawl` - 通用爬虫
- `POST /crawler/crawl_jobs` - 职位爬虫

当前返回占位响应，后续实现具体逻辑

## 🚀 快速开始

### 启动 FastAPI 服务

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问 API 文档: http://localhost:8000/docs

### 启动 gRPC 服务

```bash
python app/grpc/server.py
# 或
python server.py
```

## 📝 添加爬虫功能指南

### 步骤 1: 实现爬虫逻辑

编辑 `app/services/crawler_service.py`:

```python
async def crawl(self, config: CrawlerConfig) -> CrawlerResult:
    # 使用 requests + BeautifulSoup 或其他框架
    import requests
    from bs4 import BeautifulSoup
    
    response = requests.get(config.url, headers=config.headers, timeout=config.timeout)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # 提取数据
    data = {...}
    
    return CrawlerResult(
        url=config.url,
        data=data,
        timestamp=datetime.now(),
        success=True
    )
```

### 步骤 2: 实现职位爬虫

```python
async def crawl_job_positions(self, url: str) -> list[Dict[str, Any]]:
    # 爬取职位信息
    # 返回格式应与 Position 模型兼容
    positions = []
    # ... 爬虫逻辑 ...
    return positions
```

### 步骤 3: 集成到职位图生成

在路由中组合使用：

```python
# 在 app/api/routes/org_chart.py 中添加新端点
@router.post("/generate_from_url")
async def generate_from_url(url: str):
    crawler_service = CrawlerService()
    org_chart_service = OrgChartService()
    
    # 爬取职位
    positions_data = await crawler_service.crawl_job_positions(url)
    
    # 转换为 Position 模型
    positions = [Position(**p) for p in positions_data]
    
    # 生成职位图
    image_bytes = org_chart_service.generate_org_chart(positions)
    
    return Response(content=image_bytes, media_type="image/png")
```

## ✨ 架构优势

1. **模块化**: 清晰的分层结构，职责明确
2. **可扩展**: 添加新功能只需实现预留接口
3. **可测试**: 分层架构便于单元测试
4. **可维护**: 代码组织清晰，易于理解和修改
5. **向后兼容**: 保留旧的入口文件，不影响现有调用

## 📌 注意事项

1. 确保已安装所有依赖
2. 确保 Graphviz 系统工具已安装（用于生成图表）
3. gRPC 服务现在使用新的服务层，但接口保持不变
4. 旧的 `grpc_receiver/Receiver.py` 仍保留，但新的 gRPC 服务使用 `app/grpc/service_servicer.py`

## 🔄 迁移说明

- ✅ 所有现有功能已保留
- ✅ 职位图生成已整合到 FastAPI
- ✅ gRPC 服务已更新使用新服务层
- ✅ 代码已重构为模块化结构
- 🔮 爬虫功能接口已预留，等待实现
