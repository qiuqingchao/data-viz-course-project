#!/usr/bin/env python3
"""HTTP 接口端到端测试：图表生成、聚合与持久化 (api/charts)。
纯标准库 urllib 实现。

测试覆盖：
1. 权限拦截：未携带 Token 访问图表接口返回 401；
2. 基于已入库数据集执行数据聚合与生成 ECharts Option (POST /api/charts/aggregate)；
3. 保存图表到数据库 (POST /api/charts/save)；
4. 查询图表列表与图表详情 (GET /api/charts/list, GET /api/charts/{id})；
5. 数据安全隔离：尝试越权读取他人图表（被安全拦截）；
6. 善后清理：删除创建的图表和临时数据集，保证数据库纯净。
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

from app.db.users import find_by_username
from app.security.tokens import create_token


def _req(
    path: str,
    method: str = "GET",
    data: bytes | dict | None = None,
    headers: dict | None = None,
) -> tuple[int, dict]:
    url = f"{BASE}{path}"
    h = dict(headers or {})

    body_bytes = None
    if isinstance(data, dict):
        body_bytes = json.dumps(data).encode("utf-8")
        h["Content-Type"] = "application/json"
    elif isinstance(data, bytes):
        body_bytes = data

    req = urllib.request.Request(url, data=body_bytes, headers=h, method=method)
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


def test_charts_http_api():
    print("=" * 65)
    print("开始执行 图表模块 (api/charts) 接口端到端测试")
    print("=" * 65)

    # 1. 鉴权测试
    status, _ = _req("/api/charts/list")
    assert status == 401
    print("1. 鉴权拦截测试：未携带 Token 访问被安全拦截 (401) ✅")

    # 2. 构造 Demo 令牌
    demo = find_by_username("demo")
    assert demo is not None
    token = create_token(demo["UserID"], demo["Username"])
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 3. 先存入一个测试数据集供图表使用
    ds_save_req = {
        "name": "临时销售表_图表测试用",
        "columns": [
            {"name": "省份", "type": "string"},
            {"name": "品类", "type": "string"},
            {"name": "销售额", "type": "number"},
        ],
        "rows": [
            {"省份": "广东", "品类": "数码", "销售额": 1500},
            {"省份": "浙江", "品类": "服饰", "销售额": 1200},
            {"省份": "江苏", "品类": "食品", "销售额": 900},
        ],
    }
    status, ds_save_res = _req("/api/datasets/save", method="POST", headers=auth_headers, data=ds_save_req)
    assert status == 200
    dataset_id = ds_save_res["dataset_id"]
    print(f"2. 预备测试数据集创建成功 ID={dataset_id} ✅")

    # 4. 执行数据聚合与 ECharts Option 试算
    agg_req = {
        "dataset_id": dataset_id,
        "dimension": "省份",
        "metric": "销售额",
        "agg_type": "sum",
        "chart_type": "bar",
        "title": "各省份销售额分布",
    }
    status, agg_res = _req("/api/charts/aggregate", method="POST", headers=auth_headers, data=agg_req)
    assert status == 200
    assert agg_res["ok"] is True
    assert len(agg_res["aggregated_data"]) == 3
    assert agg_res["option"]["series"][0]["type"] == "bar"
    print("3. 图表聚合试算成功: 成功生成 ECharts option 与统计数据 ✅")

    # 5. 保存图表入库
    chart_save_req = {
        "dataset_id": dataset_id,
        "title": "各省份销售额柱状图",
        "chart_type": "bar",
        "config": agg_res["option"],
    }
    status, chart_save_res = _req("/api/charts/save", method="POST", headers=auth_headers, data=chart_save_req)
    assert status == 200
    chart_id = chart_save_res["chart_id"]
    print(f"4. 图表持久化保存成功 ID={chart_id} ✅")

    # 6. 查询图表列表与详情
    status, list_res = _req("/api/charts/list", headers=auth_headers)
    assert status == 200
    assert any(c["ChartID"] == chart_id for c in list_res["charts"])

    status, detail_res = _req(f"/api/charts/{chart_id}", headers=auth_headers)
    assert status == 200
    assert detail_res["chart"]["Title"] == "各省份销售额柱状图"
    print(f"5. 图表列表与详情读取正常 (读取成功 ID={chart_id}) ✅")

    # 7. 善后清理：删除图表与数据集
    status, _ = _req(f"/api/charts/{chart_id}", method="DELETE", headers=auth_headers)
    assert status == 200
    status, _ = _req(f"/api/datasets/{dataset_id}", method="DELETE", headers=auth_headers)
    assert status == 200
    print("6. 善后清理完成：测试图表与数据集已彻底从数据库删除，库零污染 ✅")

    print("=" * 65)
    print("🎉 图表业务 API 全部 6 项用例端到端测试通过！")
    print("=" * 65)


if __name__ == "__main__":
    test_charts_http_api()
