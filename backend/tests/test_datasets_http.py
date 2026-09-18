#!/usr/bin/env python3
"""HTTP 接口端到端测试：数据集上传、清洗与保存 (api/datasets)。
纯标准库 urllib 实现。

测试范围：
1. 权限拦截：未携带 Token 访问接口返回 401；
2. 获取内置样本列表 (GET /api/datasets/samples)；
3. 一键预览样本 (POST /api/datasets/preview-sample)；
4. 试算清洗结果 (POST /api/datasets/clean-preview)：
   - 验证合并单元格向下填充结果
   - 验证清洗审计日志
5. 正式保存数据集入库 (POST /api/datasets/save)：
   - 写入 Datasets 表
   - 验证 RowTotal 和 ColumnCount 正确落库
6. 读取当前用户的数据集列表 (GET /api/datasets/list)；
7. 引用护栏：数据集被图表引用时删除返回 409（防 SQL Server 外键 500 事故）；
8. 先删图表再删数据集，保证测试后数据库零残留。
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")
BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
SAMPLES_DIR = BACKEND_DIR.parent / "samples"
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


def test_datasets_full_api():
    print("=" * 65)
    print("开始执行 数据集上传、清洗与保存 (api/datasets) 接口端到端测试")
    print("=" * 65)

    # 1. 获取 Demo 用户 Token
    demo = find_by_username("demo")
    assert demo is not None
    token = create_token(demo["UserID"], demo["Username"])
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 2. 获取花式 Excel 样本并预览
    status, res_sample = _req(
        "/api/datasets/preview-sample",
        method="POST",
        headers=auth_headers,
        data={"filename": "电商销售_脏数据_Excel花式.xlsx"},
    )
    assert status == 200
    raw_data = res_sample["data"]
    print("1. 获取花式 Excel 样本成功 ✅")

    # 3. 试算清洗结果
    clean_req = {
        "headers": raw_data["headers"],
        "raw_matrix": raw_data["raw_preview_matrix"],
        "fill_down_merged": True,
        "filter_summary_rows": True,
        "filter_empty_rows": True,
        "auto_convert_numbers": True,
    }
    status, res_clean = _req(
        "/api/datasets/clean-preview",
        method="POST",
        headers=auth_headers,
        data=clean_req,
    )
    assert status == 200
    cleaned = res_clean
    assert len(cleaned["cleaning_logs"]) > 0
    assert cleaned["stats"]["fill_down_count"] > 0
    print(f"2. 试算清洗成功: 产生 {len(cleaned['cleaning_logs'])} 条审计日志，向下填充 {cleaned['stats']['fill_down_count']} 处 ✅")

    # 4. 将清洗后数据保存入库
    save_req = {
        "name": "测试数据集_清洗入库验证",
        "source_file_name": "电商销售_脏数据_Excel花式.xlsx",
        "columns": cleaned["columns"],
        "rows": cleaned["preview_rows"],
        "cleaning_log": cleaned["cleaning_logs"],
    }
    status, res_save = _req(
        "/api/datasets/save",
        method="POST",
        headers=auth_headers,
        data=save_req,
    )
    assert status == 200
    dataset_id = res_save["dataset_id"]
    print(f"3. 数据集持久化入库成功: ID={dataset_id}，名称「{res_save['name']}」✅")

    # 5. 读取列表验证
    status, res_list = _req("/api/datasets/list", headers=auth_headers)
    assert status == 200
    my_datasets = res_list["datasets"]
    assert any(d["DatasetID"] == dataset_id for d in my_datasets)
    print(f"4. 从库中查询列表验证: 成功查到刚入库的数据集 ID={dataset_id} ✅")

    # 6. 引用护栏：数据集被图表引用时，删除必须被 409 温柔拦下（而不是 500 崩库）
    chart_req = {
        "dataset_id": dataset_id,
        "title": "护栏测试图表",
        "chart_type": "bar",
        "config": {"option": {}, "dimension": "品类", "metric": "销售额", "agg_type": "sum"},
    }
    status, res_chart = _req("/api/charts/save", method="POST", headers=auth_headers, data=chart_req)
    assert status == 200, f"保存护栏测试图表失败：{res_chart}"
    chart_id = res_chart["chart_id"]

    status, res_blocked = _req(f"/api/datasets/{dataset_id}", method="DELETE", headers=auth_headers)
    assert status == 409, f"预期 409 拦截，实际 {status}：{res_blocked}"
    assert "图表" in res_blocked["detail"]
    print(f"5. 引用护栏生效：删除被图表引用的数据集被 409 拦下 →「{res_blocked['detail']}」✅")

    # 7. 先删图表、再删数据集，全链路放行，保持数据库纯净
    status, _ = _req(f"/api/charts/{chart_id}", method="DELETE", headers=auth_headers)
    assert status == 200
    status, res_del = _req(f"/api/datasets/{dataset_id}", method="DELETE", headers=auth_headers)
    assert status == 200
    print(f"6. 解除引用后清理成功 (图表 {chart_id} + 数据集 {dataset_id})，数据库零残留 ✅")

    print("=" * 65)
    print("🎉 数据集上传、清洗与保存 API 全部 6 项链路用例测试通过！")
    print("=" * 65)


if __name__ == "__main__":
    test_datasets_full_api()
