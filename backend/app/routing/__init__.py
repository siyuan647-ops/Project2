"""Hybrid follow-up intent routing pipeline with RAG enhancement."""

# 使用增强版路由（集成RAG意图识别）
from app.routing.enhanced_router import route_followup
from app.routing.types import Route, RoutingDecision

# 也导出原始路由供对比测试
from app.routing.router import route_followup as original_route_followup

__all__ = ["route_followup", "original_route_followup", "Route", "RoutingDecision"]
