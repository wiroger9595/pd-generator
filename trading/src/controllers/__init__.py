from .health_controller import router as health_router
from .line_controller import router as line_router
from .analysis_controller import router as analysis_router
from .fundamental_controller import router as fundamental_router
from .chip_controller import router as chip_router
from .news_controller import router as news_router
from .summary_controller import router as summary_router
from .trade_controller import router as trade_router

__all__ = [
    "health_router",
    "line_router",
    "analysis_router",
    "fundamental_router",
    "chip_router",
    "news_router",
    "summary_router",
    "trade_router",
]
