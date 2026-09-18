#!/usr/bin/env python3
"""HTTP 端到端测试：只读分享链路（第 7 阶段）。

用例（9 项，全部自清理）：
1. 备料：数据集 + 图表 + 两块面板的大屏；
2. 开启分享 → 拿到 32 位随机 token 与 share_path；
3. 详情接口回显 IsPublic/ShareToken（作者自己可见）；
4. 重复开启 → 幂等，返回同一 token（老师连点不会换链接）；
5. 匿名访问公开接口 → 200：布局 + 图表配置齐全，且不含任何用户字段；
6. 乱填 token → 404；长度不足 16 的 token → 404（数据层护栏）；
7. 关闭分享 → 旧链接【立即】404；
8. 重新开启 → 换新 token（旧链接即使被人存下也无法死灰复燃）；
9. 清理：删大屏/图表/数据集。
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
    print("开始执行 只读分享链路端到端测试")
    print("=" * 65)

    demo = find_by_username("demo")
    assert demo, "demo 账号不存在？"
    headers = {"Authorization": f"Bearer {create_token(demo['UserID'], demo['Username'])}"}

    # ── 1. 备料 ──
    st, res = _req("/api/datasets/preview-sample", "POST", {"filename": "电商销售_干净数据.csv"}, headers)
    raw = res["data"]
    st, res = _req(
        "/api/datasets/clean-preview",
        "POST",
        {
            "headers": raw["headers"],
            "raw_matrix": raw["raw_preview_matrix"],
            "fill_down_merged": True,
            "filter_summary_rows": True,
            "filter_empty_rows": True,
            "auto_convert_numbers": True,
        },
        headers,
    )
    cleaned = res
    st, res = _req(
        "/api/datasets/save",
        "POST",
        {
            "name": "分享测试数据集",
            "source_file_name": "电商销售_干净数据.csv",
            "columns": cleaned["columns"],
            "rows": cleaned["preview_rows"],
            "cleaning_log": cleaned["cleaning_logs"],
        },
        headers,
    )
    ds_id = res["dataset_id"]
    st, res = _req(
        "/api/charts/save",
        "POST",
        {
            "dataset_id": ds_id,
            "title": "分享测试图表",
            "chart_type": "bar",
            "config": {"option": {"xAxis": {"type": "category", "data": ["A", "B"]}, "yAxis": {"type": "value"}, "series": [{"type": "bar", "data": [1, 2]}]}},
        },
        headers,
    )
    ch_id = res["chart_id"]
    st, res = _req(
        "/api/dashboards/save",
        "POST",
        {
            "title": "分享测试大屏",
            "layout": {"canvas": {"w": 1920, "h": 1080}, "items": [
                {"id": "p1", "chart_id": ch_id, "x": 60, "y": 60, "w": 720, "h": 440, "z": 1},
                {"id": "p2", "chart_id": ch_id, "x": 820, "y": 60, "w": 720, "h": 440, "z": 2},
            ]},
        },
        headers,
    )
    db_id = res["dashboard_id"]
    print(f"1. 备料完成：数据集 {ds_id} + 图表 {ch_id} + 大屏 {db_id} ✅")

    # ── 2. 开启分享 ──
    st, res = _req(f"/api/dashboards/{db_id}/share", "POST", None, headers)
    assert st == 200 and res.get("share_token"), f"开启分享失败 {st}: {res}"
    token = res["share_token"]
    assert len(token) >= 16, "token 太短，可被枚举"
    assert res["share_path"] == f"/#/share/{token}", "share_path 格式异常"
    print(f"2. 开启分享 → token({len(token)}位) 与链接路径正确 ✅")

    # ── 3. 详情回显分享态 ──
    st, res = _req(f"/api/dashboards/{db_id}", headers=headers)
    dash = res["dashboard"]
    assert dash["IsPublic"] is True and dash["ShareToken"] == token, "详情未回显分享状态"
    print("3. 作者详情接口回显 IsPublic/ShareToken ✅")

    # ── 4. 幂等：重复开启返回同一 token ──
    st, res = _req(f"/api/dashboards/{db_id}/share", "POST", None, headers)
    assert res["share_token"] == token, "重复开启换了 token（老师点两下链接就变了）"
    print("4. 重复开启幂等：链接不变 ✅")

    # ── 5. 匿名读取（不带任何 Authorization）──
    st, res = _req(f"/api/share/dashboards/{token}")
    assert st == 200 and res["dashboard"]["Title"] == "分享测试大屏", f"匿名访问失败 {st}: {res}"
    assert len(res["charts"]) == 1, "两块面板引用同一图表应去重为 1 份配置"
    assert res["charts"][0]["config"]["option"]["series"][0]["data"] == [1, 2], "图表配置不完整"
    blob = json.dumps(res, ensure_ascii=False)
    assert "UserID" not in blob and "Username" not in blob and "Password" not in blob, "公开接口泄露了用户字段！"
    assert "ShareToken" not in blob, "公开响应不应再暴露 token"
    print("5. 匿名访问：布局+图表配置齐全、无任何用户信息泄露 ✅")

    # ── 6. 无效 token 一律 404 ──
    st, _ = _req("/api/share/dashboards/" + "x" * 32)
    assert st == 404, "乱填 token 竟然通过了"
    st, _ = _req("/api/share/dashboards/short")
    assert st == 404, "短 token 护栏失效"
    print("6. 乱 token / 短 token 均 404 ✅")

    # ── 7. 关闭分享 → 旧链接立即失效 ──
    st, res = _req(f"/api/dashboards/{db_id}/share", "DELETE", None, headers)
    assert st == 200, f"关闭分享失败 {st}: {res}"
    st, _ = _req(f"/api/share/dashboards/{token}")
    assert st == 404, "关闭后旧链接仍可访问（泄露窗口）！"
    print("7. 关闭分享 → 旧链接立即 404 ✅")

    # ── 8. 重新开启换新 token ──
    st, res = _req(f"/api/dashboards/{db_id}/share", "POST", None, headers)
    token2 = res["share_token"]
    assert token2 and token2 != token, "重开分享未换新 token"
    st, _ = _req(f"/api/share/dashboards/{token2}")
    assert st == 200, "新 token 反而不可用"
    print("8. 重新开启换新 token，新链接可用 ✅")

    # ── 9. 清理 ──
    _req(f"/api/dashboards/{db_id}", "DELETE", None, headers)
    _req(f"/api/charts/{ch_id}", "DELETE", None, headers)
    _req(f"/api/datasets/{ds_id}", "DELETE", None, headers)
    st, res = _req("/api/health")
    tc = res["table_counts"]
    print(f"9. 清理完成，当前表计数 {tc} ✅")

    print("=" * 65)
    print("🎉 只读分享链路全部 9 项用例端到端测试通过！")
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
