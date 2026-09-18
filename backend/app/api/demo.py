"""一键体验（第 8 阶段）API —— 写库版流程演示 + 一键清空。

提供两个接口（都要登录，都只作用于当前账号）：
1. POST /api/demo/seed   —— 后端一口气跑完真实管道：
     读内置样本 → DataCleaner 清洗 → 聚合出 4 张图 → 拼成 2×2 大屏，全部入库。
     与用户手工操作走的是同一批函数（见 app/services/demo_seeder.py 的说明），
     演示"上传→清洗→图表→大屏"整条链路真实可用。
2. POST /api/demo/reset  —— 清空当前账号的全部数据（大屏 → 图表 → 数据集），
     演示完一键复原，服务器不留垃圾。

为什么 seed 不带参数：体验流程要"笨到点一下就行"，参数越多越容易演示出错。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import current_user
from app.services.demo_seeder import reset_user_data, seed_demo_data

router = APIRouter(prefix="/api/demo", tags=["一键体验"])


@router.post("/seed", summary="为当前账号生成一套真实入库的体验数据")
async def demo_seed(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    try:
        result = seed_demo_data(user["UserID"])
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="服务器上的样本文件缺失，无法生成体验数据",
        ) from e
    return {
        "ok": True,
        **result,
        "message": (
            f"体验数据已生成：{result['row_count']} 行销售单 + 4 张图表 + 1 块大屏，"
            "和手工操作走同一条管道"
        ),
    }


@router.post("/reset", summary="清空当前账号的全部数据（二次确认在前端做）")
async def demo_reset(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    removed = reset_user_data(user["UserID"])
    return {
        "ok": True,
        "removed": removed,
        "message": (
            f"已清空：{removed['dashboards']} 块大屏、{removed['charts']} 张图表、"
            f"{removed['datasets']} 个数据集"
        ),
    }
