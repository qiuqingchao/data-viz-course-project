"""数据聚合与透视计算引擎。

为图表模块提供计算能力：
根据选定的「分类维度」和「数值指标」，对数据表执行分组聚合。

支持的聚合算法：
1. SUM（求和）：如各省份的销售总额、各品类的总订单量；
2. AVG（平均值）：如各月份的平均客单价、平均订单额；
3. COUNT（计数）：如各省份的订单笔数、记录频次；
4. MAX / MIN（极值）：如最高单笔销售额、最低采购价；

支持的排序与截断（TOP N）：
1. 升序 / 降序；
2. 限制取前 N 项（如“销售额 Top 10 省份”）。
"""

from __future__ import annotations

from typing import Any


def aggregate_data(
    rows: list[dict[str, Any]],
    dimension: str,
    metric: str,
    agg_type: str = "sum",
    sort_order: str = "desc",  # "desc" | "asc" | "none"
    limit: int = 0,  # 0 为不限制
) -> list[dict[str, Any]]:
    """对数据字典列表执行单维度 + 单指标聚合。

    返回格式形如：
    [
        {"dimension": "广东", "value": 15420.5, "count": 12},
        {"dimension": "浙江", "value": 12890.0, "count": 10},
        ...
    ]
    """
    if not rows or not dimension:
        return []

    agg_type = agg_type.lower()
    groups: dict[str, list[float | int]] = {}
    
    # 分组归类
    for r in rows:
        dim_val = r.get(dimension)
        dim_key = str(dim_val).strip() if dim_val is not None else "(空)"
        
        # 提取指标值
        if agg_type == "count":
            groups.setdefault(dim_key, []).append(1)
        else:
            raw_val = r.get(metric)
            num_val = 0.0
            if raw_val is not None and raw_val != "":
                try:
                    num_val = float(raw_val)
                except (ValueError, TypeError):
                    num_val = 0.0
            groups.setdefault(dim_key, []).append(num_val)

    result: list[dict[str, Any]] = []
    for dim_key, val_list in groups.items():
        if agg_type == "sum":
            computed = round(sum(val_list), 2)
        elif agg_type == "avg":
            computed = round(sum(val_list) / len(val_list), 2) if val_list else 0.0
        elif agg_type == "count":
            computed = len(val_list)
        elif agg_type == "max":
            computed = round(max(val_list), 2) if val_list else 0.0
        elif agg_type == "min":
            computed = round(min(val_list), 2) if val_list else 0.0
        else:
            computed = round(sum(val_list), 2)

        # 整数友好显示
        if isinstance(computed, float) and computed.is_integer():
            computed = int(computed)

        result.append({
            "dimension": dim_key,
            "value": computed,
            "count": len(val_list),
        })

    # 排序
    if sort_order == "desc":
        result.sort(key=lambda x: x["value"], reverse=True)
    elif sort_order == "asc":
        result.sort(key=lambda x: x["value"])

    # 截断 Top N
    if limit > 0:
        result = result[:limit]

    return result


def build_echarts_option(
    chart_type: str,
    title: str,
    agg_result: list[dict[str, Any]],
    dimension_label: str,
    metric_label: str,
) -> dict[str, Any]:
    """生成与墨衡设计系统契合的 ECharts Option 配置。

    支持：
    - bar: 柱状图
    - line: 折线图（平滑曲线、面积渐变）
    - horizontal_bar: 横向条形图（带动态排行动画）
    - pie: 环形饼图 / 玫瑰图
    - scatter: 散点图
    """
    dims = [item["dimension"] for item in agg_result]
    values = [item["value"] for item in agg_result]

    # 基础通用配置
    base_option: dict[str, Any] = {
        "title": {
            "text": title,
            "left": "center",
            "top": 10,
            "textStyle": {
                "fontSize": 14,
                "fontWeight": 600,
            },
        },
        "tooltip": {
            "trigger": "item" if chart_type in ("pie", "scatter") else "axis",
            "axisPointer": {"type": "shadow" if chart_type == "bar" else "line"},
        },
        "grid": {
            "top": 60,
            "left": "6%",
            "right": "6%",
            "bottom": "10%",
            "containLabel": True,
        },
    }

    if chart_type == "bar":
        return {
            **base_option,
            "xAxis": {
                "type": "category",
                "data": dims,
                "axisLabel": {"rotate": 30 if len(dims) > 6 else 0, "interval": 0},
            },
            "yAxis": {"type": "value", "name": metric_label},
            "series": [
                {
                    "name": metric_label,
                    "type": "bar",
                    "data": values,
                    "barMaxWidth": 36,
                    "itemStyle": {"borderRadius": [4, 4, 0, 0]},
                }
            ],
        }

    elif chart_type == "line":
        return {
            **base_option,
            "xAxis": {
                "type": "category",
                "data": dims,
                "boundaryGap": False,
                "axisLabel": {"rotate": 30 if len(dims) > 6 else 0, "interval": 0},
            },
            "yAxis": {"type": "value", "name": metric_label},
            "series": [
                {
                    "name": metric_label,
                    "type": "line",
                    "smooth": True,
                    "data": values,
                    "areaStyle": {"opacity": 0.25},
                    "itemStyle": {"borderWidth": 2},
                }
            ],
        }

    elif chart_type == "horizontal_bar":
        # 横向条形图，排名从上往下降序（ECharts yAxis 需要倒序排列）
        return {
            **base_option,
            "xAxis": {"type": "value", "name": metric_label},
            "yAxis": {
                "type": "category",
                "data": dims[::-1],
                "inverse": False,
                "axisLabel": {"interval": 0},
            },
            "series": [
                {
                    "name": metric_label,
                    "type": "bar",
                    "data": values[::-1],
                    "barMaxWidth": 24,
                    "label": {"show": True, "position": "right"},
                    "itemStyle": {"borderRadius": [0, 4, 4, 0]},
                }
            ],
        }

    elif chart_type == "pie":
        pie_data = [{"name": d, "value": v} for d, v in zip(dims, values)]
        return {
            **base_option,
            "legend": {
                "bottom": 5,
                "left": "center",
                "type": "scroll",
            },
            "series": [
                {
                    "name": metric_label,
                    "type": "pie",
                    "radius": ["40%", "68%"],
                    "center": ["50%", "48%"],
                    "avoidLabelOverlap": True,
                    "itemStyle": {
                        "borderRadius": 6,
                        "borderWidth": 2,
                    },
                    "label": {
                        "show": True,
                        "formatter": "{b}: {d}%",
                    },
                    "data": pie_data,
                }
            ],
        }

    else:
        # 默认柱状图
        return build_echarts_option("bar", title, agg_result, dimension_label, metric_label)
