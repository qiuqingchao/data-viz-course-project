"""一键体验种子（第 8 阶段）—— 用真实管道为当前账号生成一套可放映的示例数据。

设计原则（答辩被问"这是不是假数据"时的答案）：
  · 不是造假：读的就是 samples/ 里那份 480 行的销售单，
    清洗走 DataCleaner、聚合走 aggregate_data、
    图表配置走 build_echarts_option、入库走 create_* ——
    与用户手工点出来的每一步**同一条代码路径**，只是把往返压成一次函数调用。
  · 全部写在当前用户名下，数据隔离规则一字未改；
  · 配套 reset：一键清空也只清当前账号，别人碰不到。

清洗规则固定为"全套自动清洗"（与前端默认勾选一致）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db import data as db_data
from app.services.chart_engine import aggregate_data, build_echarts_option
from app.services.data_cleaner import DataCleaner
from app.services.data_parser import parse_dataset_file

# 与 datasets API 同一份样本目录
SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "samples"
SAMPLE_FILE = "电商销售_干净数据.csv"

DEMO_DATASET_NAME = "体验数据·480行销售单"
DEMO_DASHBOARD_TITLE = "体验大屏·电商销售驾驶舱"

# 四张图 = 四种"演示位"：占比(饼) / 排行(横条) / 趋势(线) / 对比(柱)
CHART_SPECS: list[dict[str, Any]] = [
    {
        "title": "品类销售额占比",
        "chart_type": "pie",
        "dimension": "品类",
        "metric": "销售额",
        "agg_type": "sum",
        "sort_order": "desc",
    },
    {
        "title": "省份销售额 TOP 排行",
        "chart_type": "horizontal_bar",
        "dimension": "省份",
        "metric": "销售额",
        "agg_type": "sum",
        "sort_order": "desc",
        "limit": 10,
    },
    {
        "title": "月度销售趋势",
        "chart_type": "line",
        "dimension": "月份",
        "metric": "销售额",
        "agg_type": "sum",
        "sort_order": "asc",
    },
    {
        "title": "品类订单量对比",
        "chart_type": "bar",
        "dimension": "品类",
        "metric": "订单量",
        "agg_type": "sum",
        "sort_order": "desc",
    },
]

# 1920×1080 画布上的 2×2 布局（与手动拖出来的坐标同一量级，边距 40 格）
_LAYOUT_GRID = [
    {"x": 40, "y": 40},
    {"x": 980, "y": 40},
    {"x": 40, "y": 560},
    {"x": 980, "y": 560},
]
_PANEL_W, _PANEL_H = 900, 470


def seed_demo_data(user_id: int) -> dict[str, Any]:
    """为 user_id 生成 1 数据集 + 4 图表 + 1 大屏（2×2）。返回新建对象的 id 清单。"""
    path = SAMPLES_DIR / SAMPLE_FILE
    if not path.exists():
        raise FileNotFoundError(f"样本文件缺失：{path}")

    # ① 解析 + ② 清洗（与上传向导同一套函数）
    parsed = parse_dataset_file(path.read_bytes(), SAMPLE_FILE, preview_limit=20)
    matrix = parsed["raw_matrix"]
    cleaned = DataCleaner(
        headers=parsed["headers"],
        matrix=matrix[1:],
        fill_down_merged=True,
        filter_summary_rows=True,
        filter_empty_rows=True,
        auto_convert_numbers=True,
    ).clean()

    dataset_id = db_data.create_dataset(
        user_id=user_id,
        name=DEMO_DATASET_NAME,
        columns=cleaned["columns"],
        rows=cleaned["rows"],  # 全量入库
        source_file_name=SAMPLE_FILE,
        cleaning_log=cleaned["cleaning_logs"],
    )

    # ③ 四张图：聚合 → ECharts option → 入库（构建器的同款路径）
    chart_ids: list[int] = []
    for spec in CHART_SPECS:
        agg = aggregate_data(
            rows=cleaned["rows"],
            dimension=spec["dimension"],
            metric=spec["metric"],
            agg_type=spec.get("agg_type", "sum"),
            sort_order=spec.get("sort_order", "desc"),
            limit=spec.get("limit", 0),
        )
        option = build_echarts_option(
            chart_type=spec["chart_type"],
            title=spec["title"],
            agg_result=agg,
            dimension_label=spec["dimension"],
            metric_label=spec["metric"],
        )
        chart_ids.append(
            db_data.create_chart(
                user_id=user_id,
                title=spec["title"],
                chart_type=spec["chart_type"],
                config=option,  # 构建器同款"裸 option"存法，画布已兼容
                dataset_id=dataset_id,
            )
        )

    # ④ 大屏：2×2 布局，四张图各占一格
    layout = {
        "canvas": {"w": 1920, "h": 1080},
        "items": [
            {
                "id": f"demo-p{i + 1}",
                "chart_id": cid,
                "x": cell["x"],
                "y": cell["y"],
                "w": _PANEL_W,
                "h": _PANEL_H,
                "z": i + 1,
            }
            for i, (cid, cell) in enumerate(zip(chart_ids, _LAYOUT_GRID))
        ],
    }
    dashboard_id = db_data.create_dashboard(
        user_id=user_id, title=DEMO_DASHBOARD_TITLE, layout=layout
    )

    return {
        "dataset_id": dataset_id,
        "chart_ids": chart_ids,
        "dashboard_id": dashboard_id,
        "row_count": len(cleaned["rows"]),
    }


def reset_user_data(user_id: int) -> dict[str, int]:
    """清空当前账号的全部数据：大屏 → 图表 → 数据集（顺序防外键掣肘）。"""
    removed = {"dashboards": 0, "charts": 0, "datasets": 0}
    for row in db_data.list_dashboards(user_id):
        removed["dashboards"] += 1
        db_data.delete_dashboard(user_id, row["DashboardID"])
    for row in db_data.list_charts(user_id):
        removed["charts"] += 1
        db_data.delete_chart(user_id, row["ChartID"])
    for row in db_data.list_datasets(user_id):
        removed["datasets"] += 1
        db_data.delete_dataset(user_id, row["DatasetID"])
    return removed
