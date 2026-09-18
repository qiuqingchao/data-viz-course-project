"""图表业务 API 路由。

提供功能：
1. POST /api/charts/aggregate —— 传入数据集与维度指标，返回聚合后的统计数据与 ECharts 配置（供前端实时试算渲染）；
2. POST /api/charts/save —— 保存图表到当前登录用户名下的 Charts 表；
3. GET  /api/charts/list —— 列出当前用户创建的所有图表；
4. GET  /api/charts/{chart_id} —— 获取图表详情与 ECharts 完整配置；
5. DELETE /api/charts/{chart_id} —— 删除指定图表（具备行级隔离保护）。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.db import data as db_data
from app.services.chart_engine import aggregate_data, build_echarts_option

router = APIRouter(prefix="/api/charts", tags=["图表模块"])


class AggregateRequest(BaseModel):
    dataset_id: int | None = None
    # 也可以直接传临时 rows 和 columns（用于尚未保存入库时的即时试算）
    raw_rows: list[dict[str, Any]] | None = None
    dimension: str = Field(..., description="分类维度字段名，如'省份'")
    metric: str = Field(..., description="数值指标字段名，如'销售额'")
    agg_type: str = Field("sum", description="聚合方式：sum, avg, count, max, min")
    sort_order: str = Field("desc", description="排序方式：desc, asc, none")
    limit: int = Field(10, ge=0, le=100, description="Top N 截断，0 为不限制")
    chart_type: str = Field("bar", description="图表类型：bar, line, horizontal_bar, pie")
    title: str = Field("图表统计", description="图表标题")


class SaveChartRequest(BaseModel):
    dataset_id: int | None = None
    title: str = Field(..., min_length=1, max_length=128)
    chart_type: str = Field(..., min_length=1, max_length=32)
    config: dict[str, Any] = Field(..., description="完整的 ECharts option 及构建参数")


@router.post("/aggregate", summary="数据聚合与实时 ECharts 配置生成")
async def aggregate_chart_data(
    req: AggregateRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    user_id = user["UserID"]
    rows: list[dict[str, Any]] = []

    if req.dataset_id is not None:
        ds = db_data.get_dataset(user_id, req.dataset_id)
        if not ds:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未找到指定的数据集（或无权访问）",
            )
        try:
            rows = json.loads(ds["DataJson"])
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"数据集内容损坏无法解析: {e}",
            ) from e
    elif req.raw_rows:
        rows = req.raw_rows
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="必须提供 dataset_id 或 raw_rows 进行聚合计算",
        )

    # 执行聚合计算
    agg_result = aggregate_data(
        rows=rows,
        dimension=req.dimension,
        metric=req.metric,
        agg_type=req.agg_type,
        sort_order=req.sort_order,
        limit=req.limit,
    )

    # 构造 ECharts Option
    option = build_echarts_option(
        chart_type=req.chart_type,
        title=req.title,
        agg_result=agg_result,
        dimension_label=req.dimension,
        metric_label=req.metric,
    )

    return {
        "ok": True,
        "chart_type": req.chart_type,
        "title": req.title,
        "dimension": req.dimension,
        "metric": req.metric,
        "agg_type": req.agg_type,
        "aggregated_data": agg_result,
        "option": option,
    }


@router.post("/save", summary="保存图表到数据库")
async def save_chart(
    req: SaveChartRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    user_id = user["UserID"]

    # 如果关联了数据集，确认其归属于当前用户
    if req.dataset_id is not None:
        ds = db_data.get_dataset(user_id, req.dataset_id)
        if not ds:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="关联的数据集不存在或无权操作",
            )

    try:
        new_chart_id = db_data.create_chart(
            user_id=user_id,
            title=req.title.strip(),
            chart_type=req.chart_type.strip(),
            config=req.config,
            dataset_id=req.dataset_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"保存图表失败: {e}",
        ) from e

    return {
        "ok": True,
        "chart_id": new_chart_id,
        "title": req.title,
        "message": f"图表「{req.title}」已成功保存",
    }


@router.get("/list", summary="获取当前用户的图表列表")
async def list_charts(
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    charts = db_data.list_charts(user["UserID"])
    return {
        "ok": True,
        "charts": charts,
    }


@router.get("/{chart_id}", summary="获取图表详情")
async def get_chart_detail(
    chart_id: int,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    chart = db_data.get_chart(user["UserID"], chart_id)
    if not chart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="图表不存在或无权访问",
        )
    # 解析配置 JSON
    try:
        chart["Config"] = json.loads(chart["ConfigJson"])
    except Exception:
        chart["Config"] = {}
    return {
        "ok": True,
        "chart": chart,
    }


@router.delete("/{chart_id}", summary="删除图表")
async def delete_chart(
    chart_id: int,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    affected = db_data.delete_chart(user["UserID"], chart_id)
    if affected == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="图表不存在（或已被删除）",
        )
    return {
        "ok": True,
        "message": "图表已成功删除",
    }
