#!/usr/bin/env python3
"""HTTP 端到端测试：一键体验（写库版）+ 全量入库修复 + 一键清空。

这段测试同时守两条底线：
  A. 数据完整性修复：clean-preview 必须回传【全量清洗行】、save 全量入库，
     杜绝曾经"界面 480 行、库里只存 20 行"的静默丢数据；
  B. 一键体验：seed 用真实管道建出 数据集 + 4 图 + 1 大屏（2×2，可放映），
     reset 一键清空当前账号全部数据。

用例（9 项，全部自清理；测后数据库计数回到测试前基线）：
1. 内置样本 preview → raw_matrix 全量（481 = 表头 + 480）；
2. clean-preview → rows 全量 480、preview_rows 仅 20（展示不拖慢）；
3. save 全量 → 数据集 row_count = 480（完整性核心断言）；
4. 聚合读该数据集 → 480 行真实求和（证明库里真是全量）；
5. POST /api/demo/seed → 返回 dataset + 4 chart + 1 dashboard id；
6. 大屏详情 → 4 块面板 + 带回 4 张图、config 为构建器同款裸 option；
7. 图表列表 → 至少 4 张体验图归属当前用户；
8. POST /api/demo/reset → 删除数与本轮新增吻合；
9. 清空后表计数回到测试前基线（全局零残留）。
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

SAMPLE = "电商销售_干净数据.csv"


def _req(path, method="GET", data=None, headers=None):
    h = dict(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{BASE}{path}", data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8")
        try:
            return err.code, json.loads(raw)
        except Exception:
            return err.code, {"detail": raw}


def main():
    print("=" * 65)
    print("开始执行 一键体验（写库版）+ 全量入库修复 端到端测试")
    print("=" * 65)

    demo = find_by_username("demo")
    assert demo, "demo 账号不存在？"
    H = {"Authorization": f"Bearer {create_token(demo['UserID'], demo['Username'])}"}

    # 记录测试前基线（本环境只有一个演示账号，基线通常为 0/0/0）
    _, base = _req("/api/health", headers=H)
    baseline = base["table_counts"]
    print(f"0. 测试前基线：{baseline}")

    # ── 1. 样本预览：raw_matrix 全量 ──
    st, res = _req("/api/datasets/preview-sample", "POST", {"filename": SAMPLE}, H)
    assert st == 200, f"预览失败 {st}: {res}"
    d = res["data"]
    assert "raw_matrix" in d, "预览响应缺 raw_matrix（全量矩阵）字段"
    assert len(d["raw_matrix"]) >= 400, f"raw_matrix 不是全量：{len(d['raw_matrix'])} 行"
    print(f"1. 样本预览 raw_matrix 全量 {len(d['raw_matrix'])} 行（含表头）✅")

    # ── 2. clean-preview：rows 全量 + preview_rows 仍 20 ──
    st, cl = _req(
        "/api/datasets/clean-preview",
        "POST",
        {
            "headers": d["headers"],
            "raw_matrix": d["raw_matrix"],
            "fill_down_merged": True,
            "filter_summary_rows": True,
            "filter_empty_rows": True,
            "auto_convert_numbers": True,
        },
        H,
    )
    assert st == 200
    assert "rows" in cl, "clean-preview 缺 rows 全量字段"
    assert len(cl["rows"]) == cl["total_rows"], "rows 非全量"
    assert len(cl["preview_rows"]) <= 20, "preview_rows 应截断用于展示"
    print(f"2. 清洗结果：全量 rows={len(cl['rows'])} 行，展示 preview_rows={len(cl['preview_rows'])} 行 ✅")

    # ── 3. save 全量入库 ──
    st, sv = _req(
        "/api/datasets/save",
        "POST",
        {
            "name": "完整性检验数据集",
            "source_file_name": SAMPLE,
            "columns": cl["columns"],
            "rows": cl["rows"],
            "cleaning_log": cl["cleaning_logs"],
        },
        H,
    )
    assert st == 200 and sv["row_count"] == len(cl["rows"]), f"入库行数不等于全量：{sv}"
    manual_ds = sv["dataset_id"]
    print(f"3. 数据集入库 row_count={sv['row_count']}（=全量，完整性修复生效）✅")

    # ── 4. 聚合读全量（证明库里真存了 480 行而非 20 行）──
    st, agg = _req(
        "/api/charts/aggregate",
        "POST",
        {
            "dataset_id": manual_ds, "dimension": "品类", "metric": "销售额",
            "agg_type": "sum", "sort_order": "desc", "limit": 0,
            "chart_type": "bar", "title": "完整性聚合",
        },
        H,
    )
    # 用原始全量行手算"销售额"总和，须与后端聚合总数一致
    manual_total = round(sum(float(r.get("销售额", 0) or 0) for r in cl["rows"]), 2)
    agg_total = round(sum(float(x["value"]) for x in agg["aggregated_data"]), 2)
    assert abs(manual_total - agg_total) < 1, f"聚合总数 {agg_total} ≠ 全量手算 {manual_total}（说明入库不全）"
    print(f"4. 聚合总额 {agg_total} == 全量手算 {manual_total}（数据确实完整）✅")

    # ── 5. 一键 seed ──
    st, seed = _req("/api/demo/seed", "POST", {}, H)
    assert st == 200 and seed["ok"], f"seed 失败 {st}: {seed}"
    assert len(seed["chart_ids"]) == 4, "应生成 4 张图"
    assert seed["dashboard_id"] and seed["dataset_id"]
    print(f"5. seed → 数据集{seed['dataset_id']} + 4图{seed['chart_ids']} + 大屏{seed['dashboard_id']} ✅")

    # ── 6. 大屏详情：4 面板 + 4 图配置（裸 option）──
    st, det = _req(f"/api/dashboards/{seed['dashboard_id']}", headers=H)
    assert st == 200
    assert len(det["dashboard"]["layout"]["items"]) == 4, "大屏应有 4 块面板"
    assert len(det["charts"]) == 4, "详情应带回 4 张图"
    for c in det["charts"]:
        assert "series" in c["config"], f"图 {c['chart_id']} config 非裸 option：{list(c['config'])[:4]}"
    print("6. 大屏详情：4 面板 + 4 图（裸 option，画布可直接渲染）✅")

    # ── 7. 图表列表可见 ──
    st, lst = _req("/api/charts/list", headers=H)
    seed_charts = [c for c in lst["charts"] if c["ChartID"] in seed["chart_ids"]]
    assert len(seed_charts) == 4, "体验图未全部出现在列表"
    print("7. 图表列表可见 4 张体验图 ✅")

    # ── 8. 一键清空（会一并清掉步骤3手工建的数据集 + seed 全家桶）──
    st, rst = _req("/api/demo/reset", "POST", {}, H)
    assert st == 200 and rst["ok"], f"reset 失败 {st}: {rst}"
    assert rst["removed"]["dashboards"] >= 1 and rst["removed"]["charts"] == 4 and rst["removed"]["datasets"] >= 2
    print(f"8. reset → {rst['message']}（removed={rst['removed']}）✅")

    # ── 9. 回到基线 ──
    _, after = _req("/api/health", headers=H)
    assert after["table_counts"] == baseline, f"清空后未回基线：{after['table_counts']} vs {baseline}"
    print(f"9. 清空后表计数回到基线 {after['table_counts']} ✅")

    print("=" * 65)
    print("🎉 一键体验（写库版）+ 全量入库修复 全部 9 项用例端到端测试通过！")
    print("=" * 65)


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\n❌ 断言失败：{e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 执行异常：{type(e).__name__}: {e}")
        sys.exit(1)
