"""大屏（Dashboard）API 路由 —— 第 6 阶段：大屏组装。

提供核心接口：
1. POST   /api/dashboards/save    —— 新建大屏（标题 + 布局 JSON）；
2. GET    /api/dashboards/list    —— 当前用户的大屏列表（摘要）；
3. GET    /api/dashboards/{id}    —— 大屏详情：布局 + 一次性带回全部图表配置
                                     （大屏渲染只需要这一次请求）；
4. PUT    /api/dashboards/{id}    —— 更新标题或布局；
5. DELETE /api/dashboards/{id}    —— 删除大屏；
6. POST   /api/dashboards/{id}/share   —— 开启/获取只读分享链接（第 7 阶段）；
7. DELETE /api/dashboards/{id}/share   —— 关闭分享，原链接立即失效；
8. GET    /api/share/dashboards/{token} —— 公开只读查看（免登录，凭 token）。

布局 JSON 契约（前后端共同遵守，存进 LayoutJson 列）：
{
  "canvas": {"w": 1920, "h": 1080},          // 设计坐标系，渲染时整体等比缩放
  "items": [
    {"id": "p1", "chart_id": 12,             // 引用 Charts 表的图表
     "x": 40, "y": 90, "w": 560, "h": 340,   // 位置尺寸（设计坐标系像素）
     "z": 1}                                  // 叠放次序
  ]
}

安全要点（数据隔离的第三道门）：
    保存前逐一核对 items 里的 chart_id 是否**真的属于当前用户**。
    没有这道核对，攻击者就能把别人的图表 id 拼进自己的大屏布局里"借看"数据。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.db import data as db_data
from app.security.tokens import new_share_token

router = APIRouter(prefix="/api/dashboards", tags=["大屏组装"])

# 分享查看页专用：公开、无需登录，单独挂前缀以免混进鉴权边界
public_router = APIRouter(prefix="/api/share", tags=["分享（公开只读）"])

# 课设规模的合理上限：单屏最多 30 块面板（再多浏览器也画不动了）
MAX_ITEMS = 30
CANVAS_W = 1920
CANVAS_H = 1080


class LayoutItem(BaseModel):
    id: str = Field(..., max_length=32)
    chart_id: int
    x: float = 0
    y: float = 0
    w: float = 480
    h: float = 300
    z: int = 1


class DashboardLayout(BaseModel):
    canvas: dict[str, float] = Field(default_factory=lambda: {"w": CANVAS_W, "h": CANVAS_H})
    items: list[LayoutItem] = Field(default_factory=list)


class SaveDashboardRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=128)
    layout: DashboardLayout


class UpdateDashboardRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=128)
    layout: DashboardLayout | None = None


def _validate_and_normalize(user_id: int, layout: DashboardLayout) -> dict[str, Any]:
    """核对布局里的每个 chart_id 归属 + 把坐标夹回画布内。返回可直接落库的 dict。"""
    if len(layout.items) > MAX_ITEMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"一块大屏最多放 {MAX_ITEMS} 个图表面板",
        )

    seen: set[int] = set()
    for item in layout.items:
        if item.chart_id in seen:
            continue
        seen.add(item.chart_id)
        if not db_data.get_chart(user_id, item.chart_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"图表 {item.chart_id} 不存在或不属于当前账号，无法放入大屏",
            )

    # 坐标钳制：面板必须完整留在画布内（允许 0 ≤ x ≤ canvas.w - 最小宽度）
    clamped_items = []
    for item in layout.items:
        d = item.model_dump()
        d["w"] = max(120.0, min(float(d["w"]), float(CANVAS_W)))
        d["h"] = max(90.0, min(float(d["h"]), float(CANVAS_H)))
        d["x"] = max(0.0, min(float(d["x"]), CANVAS_W - d["w"]))
        d["y"] = max(0.0, min(float(d["y"]), CANVAS_H - d["h"]))
        clamped_items.append(d)

    return {"canvas": {"w": CANVAS_W, "h": CANVAS_H}, "items": clamped_items}


def _parse_layout(raw: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(raw.get("LayoutJson") or "{}")
    except Exception:
        return {"canvas": {"w": CANVAS_W, "h": CANVAS_H}, "items": []}


@router.post("/save", summary="新建大屏")
async def save_dashboard(
    req: SaveDashboardRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    layout_dict = _validate_and_normalize(user["UserID"], req.layout)
    dashboard_id = db_data.create_dashboard(
        user_id=user["UserID"],
        title=req.title.strip(),
        layout=layout_dict,
    )
    return {
        "ok": True,
        "dashboard_id": dashboard_id,
        "message": f"大屏「{req.title}」已保存",
    }


@router.get("/list", summary="当前用户的大屏列表")
async def list_dashboards(
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    rows = db_data.list_dashboards(user["UserID"])
    items = []
    for r in rows:
        layout = _parse_layout(r)
        items.append(
            {
                "DashboardID": r["DashboardID"],
                "Title": r["Title"],
                "ItemCount": len(layout.get("items", [])),
                "IsPublic": bool(r.get("IsPublic")),
                "CreatedAt": str(r.get("CreatedAt") or ""),
                "UpdatedAt": str(r.get("UpdatedAt") or ""),
            }
        )
    return {"ok": True, "dashboards": items}


def _charts_payload(layout: dict[str, Any], fetch) -> list[dict[str, Any]]:
    """按布局引用的 chart_id 一次性装配图表配置（去重、失效引用跳过）。

    fetch: chart_id -> row 的取数函数 —— 登录态传"隔离版"，
    分享态传"受限公开版"，两条路径共用同一装配逻辑。
    """
    charts: dict[int, Any] = {}
    for item in layout.get("items", []):
        cid = item.get("chart_id")
        if cid is None or cid in charts:
            continue
        chart = fetch(int(cid))
        if not chart:
            continue
        try:
            config = json.loads(chart.get("ConfigJson") or "{}")
        except Exception:
            config = {}
        charts[int(cid)] = {
            "chart_id": chart["ChartID"],
            "title": chart["Title"],
            "chart_type": chart["ChartType"],
            "config": config,
        }
    return list(charts.values())


@router.get("/{dashboard_id}", summary="大屏详情（布局 + 全部图表配置一次带回）")
async def get_dashboard_detail(
    dashboard_id: int,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    row = db_data.get_dashboard(user["UserID"], dashboard_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="大屏不存在或无权访问",
        )

    layout = _parse_layout(row)
    # 一次性把布局引用到的图表配置全部取出：大屏渲染只需这一个请求，
    # 避免"每块面板各发一次 HTTP"把答辩现场的网络抖成幻灯片。
    charts = _charts_payload(layout, lambda cid: db_data.get_chart(user["UserID"], cid))

    return {
        "ok": True,
        "dashboard": {
            "DashboardID": row["DashboardID"],
            "Title": row["Title"],
            "IsPublic": bool(row.get("IsPublic")),
            "ShareToken": row.get("ShareToken"),
            "layout": layout,
        },
        "charts": charts,
    }


@router.put("/{dashboard_id}", summary="更新大屏标题/布局")
async def update_dashboard(
    dashboard_id: int,
    req: UpdateDashboardRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    row = db_data.get_dashboard(user["UserID"], dashboard_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="大屏不存在或无权访问",
        )

    layout_dict = (
        _validate_and_normalize(user["UserID"], req.layout)
        if req.layout is not None
        else None
    )
    affected = db_data.update_dashboard(
        user_id=user["UserID"],
        dashboard_id=dashboard_id,
        title=req.title.strip() if req.title else None,
        layout=layout_dict,
    )
    return {
        "ok": True,
        "updated": affected > 0,
        "message": "大屏已更新" if affected else "没有需要更新的内容",
    }


@router.delete("/{dashboard_id}", summary="删除大屏")
async def delete_dashboard(
    dashboard_id: int,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    affected = db_data.delete_dashboard(user["UserID"], dashboard_id)
    if affected == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="大屏不存在或已被删除",
        )
    return {"ok": True, "message": "大屏已删除"}


# ============================================================ 只读分享（第 7 阶段）
#
# 交互模型：
#   开启分享 → 生成（或复用）随机 token，返回完整相对路径；
#   关闭分享 → token 置空、IsPublic=0，原链接【立即失效】；
#   公开查看 → 只凭 token，不需要也不能携带任何登录态。
# 安全边界：
#   token 由 secrets 生成（32 字符 URL-safe），不可枚举；
#   查询走 get_shared_dashboard（强制 IsPublic=1 + 长度校验），
#   且只回传大屏布局与其引用的图表配置，不回传任何用户信息。


@router.post("/{dashboard_id}/share", summary="开启/获取只读分享链接")
async def open_share(
    dashboard_id: int,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    row = db_data.get_dashboard(user["UserID"], dashboard_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="大屏不存在或无权访问",
        )
    token = row.get("ShareToken")
    if not token or not row.get("IsPublic"):
        # 每次重新开启都换新 token：防止"早已关闭的旧链接"死灰复燃
        token = new_share_token()
        db_data.set_share_token(user["UserID"], dashboard_id, token)
    return {
        "ok": True,
        "share_token": token,
        "share_path": f"/#/share/{token}",
        "message": "分享链接已就绪",
    }


@router.delete("/{dashboard_id}/share", summary="关闭分享（原链接立即失效）")
async def close_share(
    dashboard_id: int,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    row = db_data.get_dashboard(user["UserID"], dashboard_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="大屏不存在或无权访问",
        )
    db_data.set_share_token(user["UserID"], dashboard_id, None)
    return {"ok": True, "message": "分享已关闭，原链接立即失效"}


@public_router.get("/dashboards/{token}", summary="凭分享 token 只读查看大屏")
async def view_shared_dashboard(token: str) -> dict[str, Any]:
    row = db_data.get_shared_dashboard(token)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="分享链接无效或已被作者关闭",
        )
    layout = _parse_layout(row)
    charts = _charts_payload(layout, db_data.get_chart_for_shared_layout)
    return {
        "ok": True,
        "dashboard": {
            "Title": row["Title"],
            "layout": layout,
        },
        "charts": charts,
    }
