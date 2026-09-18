"""用户数据（数据集 / 图表 / 大屏）的读写 —— **数据隔离就落在这里**。

核心规矩（请勿破坏）：
    本文件里**每一个**函数，第一个参数都必须是 `user_id`，
    并且每条 SQL 都必须带 `UserID = ?`。

    为什么用"参数顺序 + 强制条件"这种笨办法，而不是靠自觉？
    因为隔离一旦漏一处，别人就能看到别人的数据 —— 这是本项目的核心考核点。
    用统一的写法之后，只要扫一眼函数签名，就能确认没有漏网的。

    另外还有一条：查不到、或不属于当前用户，一律返回 None / 0 条，
    **不区分"不存在"和"不是你的"** —— 这样别人也无法通过试探来猜出
    系统里有哪些数据。
"""

from __future__ import annotations

import json
from typing import Any

from .connection import execute, now_sql, query_all, query_one

# ============================================================ 数据集 Datasets

_DATASET_LIST_FIELDS = (
    "DatasetID, Name, SourceFileName, SourceSheet, RowTotal, ColumnCount, "
    "ColumnsJson, CreatedAt, UpdatedAt"
)


def list_datasets(user_id: int) -> list[dict[str, Any]]:
    """列出当前用户的数据集（只返回"目录信息"，不返回数据本体，避免拖慢页面）。"""
    return query_all(
        f"SELECT {_DATASET_LIST_FIELDS} FROM Datasets WHERE UserID = ? ORDER BY DatasetID DESC",
        [user_id],
    )


def get_dataset(user_id: int, dataset_id: int) -> dict | None:
    """取一个数据集（含数据本体）。不属于当前用户时返回 None。"""
    return query_one(
        "SELECT * FROM Datasets WHERE DatasetID = ? AND UserID = ?",
        [dataset_id, user_id],
    )


def create_dataset(
    user_id: int,
    name: str,
    columns: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    source_file_name: str | None = None,
    source_sheet: str | None = None,
    cleaning_log: list[dict[str, Any]] | None = None,
) -> int:
    return execute(
        """
        INSERT INTO Datasets
            (UserID, Name, SourceFileName, SourceSheet, RowTotal, ColumnCount,
             ColumnsJson, DataJson, CleaningLogJson)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            user_id,
            name,
            source_file_name,
            source_sheet,
            len(rows),
            len(columns),
            json.dumps(columns, ensure_ascii=False),
            json.dumps(rows, ensure_ascii=False),
            json.dumps(cleaning_log or [], ensure_ascii=False),
        ],
    )


def update_dataset(
    user_id: int,
    dataset_id: int,
    *,
    name: str | None = None,
    columns: list[dict[str, Any]] | None = None,
    rows: list[dict[str, Any]] | None = None,
    cleaning_log: list[dict[str, Any]] | None = None,
) -> int:
    """改名 / 覆盖数据（清洗之后回写）。只影响当前用户自己的那一行。"""
    sets: list[str] = []
    params: list[Any] = []
    if name is not None:
        sets.append("Name = ?")
        params.append(name)
    if columns is not None:
        sets.append("ColumnsJson = ?")
        params.append(json.dumps(columns, ensure_ascii=False))
        sets.append("ColumnCount = ?")
        params.append(len(columns))
    if rows is not None:
        sets.append("DataJson = ?")
        params.append(json.dumps(rows, ensure_ascii=False))
        sets.append("RowTotal = ?")
        params.append(len(rows))
    if cleaning_log is not None:
        sets.append("CleaningLogJson = ?")
        params.append(json.dumps(cleaning_log, ensure_ascii=False))

    if not sets:
        return 0

    sets.append(f"UpdatedAt = {now_sql()}")
    params.extend([dataset_id, user_id])
    return execute(
        f"UPDATE Datasets SET {', '.join(sets)} WHERE DatasetID = ? AND UserID = ?",
        params,
    )


def count_charts_using_dataset(user_id: int, dataset_id: int) -> int:
    """删除数据集前的引用体检：有多少张图表还骑在这份数据上。"""
    row = query_one(
        "SELECT COUNT(*) AS n FROM Charts WHERE UserID = ? AND DatasetID = ?",
        [user_id, dataset_id],
    )
    return int(row["n"]) if row else 0


def delete_dataset(user_id: int, dataset_id: int) -> int:
    return execute("DELETE FROM Datasets WHERE DatasetID = ? AND UserID = ?", [dataset_id, user_id])


def count_datasets(user_id: int) -> int:
    row = query_one("SELECT COUNT(*) AS n FROM Datasets WHERE UserID = ?", [user_id])
    return int(row["n"]) if row else 0


# ================================================================ 图表 Charts


def list_charts(user_id: int) -> list[dict[str, Any]]:
    return query_all(
        "SELECT ChartID, DatasetID, Title, ChartType, ConfigJson, CreatedAt, UpdatedAt "
        "FROM Charts WHERE UserID = ? ORDER BY ChartID DESC",
        [user_id],
    )


def get_chart(user_id: int, chart_id: int) -> dict | None:
    return query_one("SELECT * FROM Charts WHERE ChartID = ? AND UserID = ?", [chart_id, user_id])


# --------------------------------------------------------------------------
# ⚠️ 第二个**故意不做用户隔离**的只读查询（第一个是 get_shared_dashboard）。
#
# 唯一合法用途：渲染"分享链接"大屏时，按布局里已列出的 chart_id 取图表配置。
# 这些 chart_id 来自一张 IsPublic=1 且经 token 校验的大屏，token 本身即钥匙；
# 除它以外任何接口都不得调用本函数 —— 用户自己路径上的读取一律用 get_chart。
# --------------------------------------------------------------------------
def get_chart_for_shared_layout(chart_id: int) -> dict | None:
    return query_one("SELECT * FROM Charts WHERE ChartID = ?", [chart_id])


def create_chart(
    user_id: int,
    title: str,
    chart_type: str,
    config: dict[str, Any],
    dataset_id: int | None = None,
) -> int:
    return execute(
        """
        INSERT INTO Charts (UserID, DatasetID, Title, ChartType, ConfigJson)
        VALUES (?, ?, ?, ?, ?)
        """,
        [user_id, dataset_id, title, chart_type, json.dumps(config, ensure_ascii=False)],
    )


def update_chart(
    user_id: int,
    chart_id: int,
    *,
    title: str | None = None,
    config: dict[str, Any] | None = None,
) -> int:
    sets: list[str] = []
    params: list[Any] = []
    if title is not None:
        sets.append("Title = ?")
        params.append(title)
    if config is not None:
        sets.append("ConfigJson = ?")
        params.append(json.dumps(config, ensure_ascii=False))
    if not sets:
        return 0
    sets.append(f"UpdatedAt = {now_sql()}")
    params.extend([chart_id, user_id])
    return execute(f"UPDATE Charts SET {', '.join(sets)} WHERE ChartID = ? AND UserID = ?", params)


def delete_chart(user_id: int, chart_id: int) -> int:
    return execute("DELETE FROM Charts WHERE ChartID = ? AND UserID = ?", [chart_id, user_id])


def count_charts(user_id: int) -> int:
    row = query_one("SELECT COUNT(*) AS n FROM Charts WHERE UserID = ?", [user_id])
    return int(row["n"]) if row else 0


# ============================================================ 大屏 Dashboards


def list_dashboards(user_id: int) -> list[dict[str, Any]]:
    return query_all(
        "SELECT DashboardID, Title, LayoutJson, IsPublic, ShareToken, CreatedAt, UpdatedAt "
        "FROM Dashboards WHERE UserID = ? ORDER BY DashboardID DESC",
        [user_id],
    )


def get_dashboard(user_id: int, dashboard_id: int) -> dict | None:
    return query_one(
        "SELECT * FROM Dashboards WHERE DashboardID = ? AND UserID = ?",
        [dashboard_id, user_id],
    )


def create_dashboard(user_id: int, title: str, layout: dict[str, Any]) -> int:
    return execute(
        "INSERT INTO Dashboards (UserID, Title, LayoutJson, IsPublic) VALUES (?, ?, ?, 0)",
        [user_id, title, json.dumps(layout, ensure_ascii=False)],
    )


def update_dashboard(
    user_id: int,
    dashboard_id: int,
    *,
    title: str | None = None,
    layout: dict[str, Any] | None = None,
) -> int:
    sets: list[str] = []
    params: list[Any] = []
    if title is not None:
        sets.append("Title = ?")
        params.append(title)
    if layout is not None:
        sets.append("LayoutJson = ?")
        params.append(json.dumps(layout, ensure_ascii=False))
    if not sets:
        return 0
    sets.append(f"UpdatedAt = {now_sql()}")
    params.extend([dashboard_id, user_id])
    return execute(
        f"UPDATE Dashboards SET {', '.join(sets)} WHERE DashboardID = ? AND UserID = ?", params
    )


def delete_dashboard(user_id: int, dashboard_id: int) -> int:
    return execute(
        "DELETE FROM Dashboards WHERE DashboardID = ? AND UserID = ?", [dashboard_id, user_id]
    )


def count_dashboards(user_id: int) -> int:
    row = query_one("SELECT COUNT(*) AS n FROM Dashboards WHERE UserID = ?", [user_id])
    return int(row["n"]) if row else 0


def set_share_token(user_id: int, dashboard_id: int, token: str | None) -> int:
    """开启/关闭只读分享。token 为空表示关闭分享。"""
    return execute(
        "UPDATE Dashboards SET ShareToken = ?, IsPublic = ? WHERE DashboardID = ? AND UserID = ?",
        [token, 1 if token else 0, dashboard_id, user_id],
    )


# --------------------------------------------------------------------------
# ⚠️ 唯一一个**故意不做用户隔离**的查询。
#
# 它服务于"只读分享链接"：拿到链接的人不需要登录也能看。
# 因此必须极其克制：
#   1. 只有 IsPublic = 1（用户主动开过分享）的才返回；
#   2. 只返回大屏本身，**不返回任何用户信息**；
#   3. token 是随机长串，猜不出来。
# 这两个条件缺一个，都会变成"数据泄露"。
# --------------------------------------------------------------------------
def get_shared_dashboard(token: str) -> dict | None:
    if not token or len(token) < 16:
        return None
    return query_one(
        "SELECT DashboardID, Title, LayoutJson, CreatedAt FROM Dashboards "
        "WHERE ShareToken = ? AND IsPublic = 1",
        [token],
    )
