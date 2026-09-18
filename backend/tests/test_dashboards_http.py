#!/usr/bin/env python3
"""HTTP 端到端测试：大屏组装 API (api/dashboards)。

用例（7 项，全部自清理，保证测试后数据库零残留）：
1. 备料：保存一份数据集 + 一张图表；
2. 新建大屏（两块面板的布局）→ 返回 dashboard_id；
3. 列表接口能看到大屏，ItemCount 正确；
4. 详情接口一次带回布局 + 全部图表配置；
5. PUT 更新布局（移动面板坐标）→ 详情里坐标确实变了；
6. 越权护栏：布局里塞一个不存在的 chart_id → 必须 400 拒收；
7. 删除大屏 → 404 确认已消失 → 清理图表与数据集。
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")
BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.db.users import find_by_username  # noqa: E402
from app.security.tokens import create_token  # noqa: E402


def _req(path, method="GET", data=None, headers=None):
    h = dict(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{BASE}{path}", data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8")
        try:
            return err.code, json.loads(raw)
        except Exception:
            return err.code, {"detail": raw}


def main():
    print("=" * 65)
    print("开始执行 大屏组装 API (api/dashboards) 端到端测试")
    print("=" * 65)

    demo = find_by_username("demo")
    assert demo, "demo 账号不存在？"
    headers = {"Authorization": f"Bearer {create_token(demo['UserID'], demo['Username'])}"}

    # ── 1. 备料：数据集 + 图表 ──
    st, res = _req(
        "/api/datasets/preview-sample",
        method="POST",
        headers=headers,
        data={"filename": "电商销售_干净数据.csv"},
    )
    assert st == 200, f"样本预览失败 {st}: {res}"
    raw = res["data"]
    st, res = _req(
        "/api/datasets/clean-preview",
        method="POST",
        headers=headers,
        data={
            "headers": raw["headers"],
            "raw_matrix": raw["raw_preview_matrix"],
            "fill_down_merged": True,
            "filter_summary_rows": True,
            "filter_empty_rows": True,
            "auto_convert_numbers": True,
        },
    )
    assert st == 200
    cleaned = res
    st, res = _req(
        "/api/datasets/save",
        method="POST",
        headers=headers,
        data={
            "name": "大屏测试数据集",
            "source_file_name": "电商销售_干净数据.csv",
            "columns": cleaned["columns"],
            "rows": cleaned["preview_rows"],
            "cleaning_log": cleaned["cleaning_logs"],
        },
    )
    assert st == 200, f"保存数据集失败 {st}: {res}"
    dataset_id = res["dataset_id"]

    st, res = _req(
        "/api/charts/save",
        method="POST",
        headers=headers,
        data={
            "dataset_id": dataset_id,
            "title": "大屏测试图表",
            "chart_type": "bar",
            "config": {"option": {"title": {"text": "测试"}, "series": []}},
        },
    )
    assert st == 200, f"保存图表失败 {st}: {res}"
    chart_id = res["chart_id"]
    print(f"1. 备料完成：数据集 {dataset_id} + 图表 {chart_id} ✅")

    # ── 2. 新建大屏 ──
    layout = {
        "canvas": {"w": 1920, "h": 1080},
        "items": [
            {"id": "p1", "chart_id": chart_id, "x": 40, "y": 120, "w": 900, "h": 420, "z": 1},
            {"id": "p2", "chart_id": chart_id, "x": 980, "y": 120, "w": 900, "h": 420, "z": 2},
        ],
    }
    st, res = _req(
        "/api/dashboards/save",
        method="POST",
        headers=headers,
        data={"title": "端到端测试大屏", "layout": layout},
    )
    assert st == 200, f"新建大屏失败 {st}: {res}"
    dash_id = res["dashboard_id"]
    print(f"2. 新建大屏成功 ID={dash_id} ✅")

    # ── 3. 列表 ──
    st, res = _req("/api/dashboards/list", headers=headers)
    assert st == 200
    mine = [d for d in res["dashboards"] if d["DashboardID"] == dash_id]
    assert mine and mine[0]["ItemCount"] == 2, f"列表缺项或计数错: {mine}"
    print("3. 列表可见且面板计数正确 ✅")

    # ── 4. 详情：一次带回布局 + 图表配置 ──
    st, res = _req(f"/api/dashboards/{dash_id}", headers=headers)
    assert st == 200
    assert len(res["dashboard"]["layout"]["items"]) == 2
    assert len(res["charts"]) == 1 and res["charts"][0]["config"]["option"]["title"]["text"] == "测试"
    print("4. 详情接口一次带回布局 + 图表配置 ✅")

    # ── 5. 更新布局：移动 p1 ──
    moved = json.loads(json.dumps(layout))
    moved["items"][0]["x"] = 300
    moved["items"][0]["y"] = 500
    st, res = _req(
        f"/api/dashboards/{dash_id}",
        method="PUT",
        headers=headers,
        data={"layout": moved},
    )
    assert st == 200 and res["updated"]
    st, res = _req(f"/api/dashboards/{dash_id}", headers=headers)
    p1 = [i for i in res["dashboard"]["layout"]["items"] if i["id"] == "p1"][0]
    assert p1["x"] == 300 and p1["y"] == 500, f"坐标未更新: {p1}"
    print("5. 布局更新成功，面板新坐标已落库 ✅")

    # ── 6. 越权护栏：塞不存在的图表 ID ──
    bad = {"canvas": {"w": 1920, "h": 1080}, "items": [{"id": "x", "chart_id": 99999999, "x": 0, "y": 0, "w": 400, "h": 300, "z": 1}]}
    st, res = _req(
        "/api/dashboards/save",
        method="POST",
        headers=headers,
        data={"title": "非法大屏", "layout": bad},
    )
    assert st == 400, f"越权布局应被 400 拒绝，实际 {st}"
    assert "不存在或不属于" in res["detail"]
    print(f"6. 越权护栏生效：{res['detail']} ✅")

    # ── 7. 删除 + 全链路清理 ──
    st, _ = _req(f"/api/dashboards/{dash_id}", method="DELETE", headers=headers)
    assert st == 200
    st, _ = _req(f"/api/dashboards/{dash_id}", method="DELETE", headers=headers)
    assert st == 404
    st, _ = _req(f"/api/charts/{chart_id}", method="DELETE", headers=headers)
    assert st == 200
    st, _ = _req(f"/api/datasets/{dataset_id}", method="DELETE", headers=headers)
    assert st == 200
    print("7. 删除大屏 → 再删返回 404 → 测试数据全部清干净 ✅")

    print("=" * 65)
    print("🎉 大屏组装 API 全部 7 项链路用例测试通过！")
    print("=" * 65)


if __name__ == "__main__":
    main()
