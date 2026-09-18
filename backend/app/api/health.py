"""接口层：把后端的能力暴露成"网址"，前端通过网址来问后端。

第 1 阶段只有一个网址：/api/health （体检）
"""

from __future__ import annotations

from fastapi import APIRouter

from app.services.health_check import health_snapshot

router = APIRouter(prefix="/api", tags=["系统"])


@router.get("/health", summary="体检：后端是否活着、数据库通不通")
def health() -> dict:
    return health_snapshot()
