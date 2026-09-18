"""「体检」逻辑：检查后端自己活着没有、数据库通不通、各模块到位没有。

设计原则：**体检本身绝不能把服务搞崩**。
所以这里所有外部调用都用 try/except 包住，任何异常都转成"如实报告"，
而不是抛出去。使用者看到"数据库连不上"远比看到"网页打不开"有用得多。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.config import settings


def _check_active_database() -> dict[str, Any]:
    """体检**当前正在使用**的那个数据库（本地库或学校库）。"""
    from app.db.connection import ping

    ok, message = ping()
    if settings.db_mode == "mssql":
        target = f"{settings.mssql_host}:{settings.mssql_port}/{settings.mssql_database or '(未填库名)'}"
    else:
        target = str(settings.sqlite_path)
    return {"connected": ok, "message": message, "target": target}


def _check_school_database() -> dict[str, Any]:
    """额外报告学校数据库"还差什么"，方便使用者知道下一步该做什么。"""
    if settings.db_mode == "mssql":
        return {
            "connected": True,
            "message": "当前正在使用学校数据库",
            "target": f"{settings.mssql_host}:{settings.mssql_port}",
        }

    missing: list[str] = []
    if not settings.mssql_host:
        missing.append("数据库地址")
    if not settings.mssql_database:
        missing.append("库名")
    if not settings.mssql_user:
        missing.append("用户名")
    if not settings.mssql_password:
        missing.append("密码（由你自己填进 backend/.env）")

    driver = None
    for module_name in ("pyodbc", "pymssql"):
        try:
            __import__(module_name)
            driver = module_name
            break
        except ImportError:
            continue

    if missing:
        return {
            "connected": False,
            "message": "还差：" + "、".join(missing),
            "target": f"{settings.mssql_host}:{settings.mssql_port}" if settings.mssql_host else "",
        }
    if driver is None:
        return {
            "connected": False,
            "message": "信息已填全，但缺少连接驱动（需要你同意后再安装）",
            "target": f"{settings.mssql_host}:{settings.mssql_port}",
        }
    return {
        "connected": False,
        "message": f"驱动 {driver} 已就绪，正在使用本地兜底库",
        "target": f"{settings.mssql_host}:{settings.mssql_port}",
    }


def check_database() -> dict[str, Any]:
    active = _check_active_database()
    active["mode"] = settings.db_mode
    active["mode_label"] = settings.db_mode_label
    active["school"] = _check_school_database()
    return active


def _table_counts() -> dict[str, int]:
    """各张表里有多少条数据（给体检接口用，也是"数据有没有真落库"的证据）。"""
    from app.db.connection import query_one

    out: dict[str, int] = {}
    for table, key in (
        ("Users", "用户"),
        ("Datasets", "数据集"),
        ("Charts", "图表"),
        ("Dashboards", "大屏"),
    ):
        try:
            row = query_one(f"SELECT COUNT(*) AS n FROM {table}")
            out[key] = int(row["n"]) if row else 0
        except Exception:
            out[key] = -1  # -1 表示"查不了"，不假装是 0
    return out


def health_snapshot() -> dict[str, Any]:
    from app.main import startup_report

    db = check_database()

    tables: dict[str, int] = {}
    if db["connected"]:
        try:
            tables = _table_counts()
        except Exception as exc:  # noqa: BLE001
            tables = {"错误": -1}
            db["message"] = f"{db['message']}；统计表行数失败：{exc}"

    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.version,
        "environment": settings.app_env,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "database": db,
        "table_counts": tables,
        "startup": startup_report,
        "modules_ready": {
            "骨架与握手": True,
            "用户与权限": True,  # 第 3 阶段完成
            "数据处理": False,
            "图表渲染": False,
            "大屏搭建": False,
            "导出与分享": False,
            "示例数据": False,
        },
    }
