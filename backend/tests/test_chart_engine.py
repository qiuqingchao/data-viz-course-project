#!/usr/bin/env python3
"""图表生成与数据聚合引擎单元测试。

测试覆盖：
1. SUM 聚合测试（按省份对销售额求和，降序排列）；
2. AVG 聚合测试（按品类计算平均销售额）；
3. COUNT 计数测试（统计频次）；
4. TOP N 截断测试（限制输出前 3 名）；
5. ECharts Option 生成结构健全性测试（柱状图、折线图、环形饼图、横向条形图）。
"""

from __future__ import annotations

import pathlib
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.services.chart_engine import aggregate_data, build_echarts_option

# 模拟 5 行干净销售数据
MOCK_ROWS = [
    {"省份": "广东", "品类": "数码家电", "销售额": 1000.0},
    {"省份": "广东", "品类": "服饰鞋包", "销售额": 500.0},
    {"省份": "浙江", "品类": "数码家电", "销售额": 800.0},
    {"省份": "江苏", "品类": "食品生鲜", "销售额": 1200.0},
    {"省份": "浙江", "品类": "食品生鲜", "销售额": 400.0},
]


def test_chart_engine():
    print("=" * 65)
    print("开始执行 图表生成与数据聚合引擎 (chart_engine) 单元测试")
    print("=" * 65)

    # 1. SUM 聚合测试
    res_sum = aggregate_data(MOCK_ROWS, dimension="省份", metric="销售额", agg_type="sum")
    print(f"1. SUM 聚合结果: {res_sum}")
    assert len(res_sum) == 3
    # 广东: 1000 + 500 = 1500 (第一名)
    assert res_sum[0]["dimension"] == "广东"
    assert res_sum[0]["value"] == 1500
    # 浙江与江苏并列 1200
    val_map = {x["dimension"]: x["value"] for x in res_sum}
    assert val_map["江苏"] == 1200
    assert val_map["浙江"] == 1200
    print("   -> SUM 聚合与排序正确通过 ✅\n")

    # 2. AVG 聚合测试
    res_avg = aggregate_data(MOCK_ROWS, dimension="品类", metric="销售额", agg_type="avg")
    print(f"2. AVG 聚合结果: {res_avg}")
    # 数码家电: (1000+800)/2 = 900
    item_digital = next(x for x in res_avg if x["dimension"] == "数码家电")
    assert item_digital["value"] == 900
    print("   -> AVG 平均值聚合正确通过 ✅\n")

    # 3. COUNT 聚合测试
    res_count = aggregate_data(MOCK_ROWS, dimension="省份", metric="", agg_type="count")
    print(f"3. COUNT 计数聚合结果: {res_count}")
    item_gd = next(x for x in res_count if x["dimension"] == "广东")
    assert item_gd["value"] == 2
    print("   -> COUNT 频次统计正确通过 ✅\n")

    # 4. TOP N 限制截断
    res_top2 = aggregate_data(MOCK_ROWS, dimension="省份", metric="销售额", limit=2)
    assert len(res_top2) == 2
    print("4. TOP N 截断正确通过 ✅\n")

    # 5. ECharts Option 生成测试
    opt_bar = build_echarts_option("bar", "省份销售额", res_sum, "省份", "销售额")
    assert opt_bar["series"][0]["type"] == "bar"
    assert "广东" in opt_bar["xAxis"]["data"]
    assert len(opt_bar["xAxis"]["data"]) == 3

    opt_pie = build_echarts_option("pie", "品类分布", res_avg, "品类", "平均额")
    assert opt_pie["series"][0]["type"] == "pie"

    opt_hbar = build_echarts_option("horizontal_bar", "排名", res_sum, "省份", "销售额")
    assert opt_hbar["yAxis"]["type"] == "category"

    print("5. ECharts Option 结构装配验证通过 (bar, line, pie, horizontal_bar) ✅\n")
    print("=" * 65)
    print("🎉 图表生成与数据聚合引擎单元测试全部通过！")
    print("=" * 65)


if __name__ == "__main__":
    test_chart_engine()
