"""用户表的读写。

注意这一层的定位：它管的是"账号本身"（注册、登录、改密码），
**不属于"用户数据隔离"的范畴** —— 登录时必须能按用户名查到人，
这是设计使然。真正需要隔离的是 Datasets / Charts / Dashboards，
那些在 data.py 里，那边每个函数都强制带 user_id。
"""

from __future__ import annotations

from typing import Any

from .connection import execute, now_sql, query_all, query_one

# 对外返回用户信息时，**永远不带密码字段**
SAFE_FIELDS = "UserID, Username, DisplayName, Role, IsActive, CreatedAt, LastLoginAt"


def create_user(
    username: str,
    password_hash: str,
    display_name: str | None = None,
    role: str = "student",
) -> int:
    return execute(
        """
        INSERT INTO Users (Username, PasswordHash, DisplayName, Role, IsActive)
        VALUES (?, ?, ?, ?, 1)
        """,
        [username, password_hash, display_name or username, role],
    )


def find_by_username(username: str) -> dict | None:
    """登录用：需要拿到 PasswordHash 做校验，所以这里带密码字段。
    调用方（登录接口）用完必须立刻丢弃，不得回传给前端。"""
    return query_one(
        "SELECT UserID, Username, PasswordHash, DisplayName, Role, IsActive FROM Users WHERE Username = ?",
        [username],
    )


def find_by_id(user_id: int) -> dict | None:
    return query_one(f"SELECT {SAFE_FIELDS} FROM Users WHERE UserID = ?", [user_id])


def touch_last_login(user_id: int) -> None:
    execute(f"UPDATE Users SET LastLoginAt = {now_sql()} WHERE UserID = ?", [user_id])


def update_password_hash(user_id: int, password_hash: str) -> int:
    return execute("UPDATE Users SET PasswordHash = ? WHERE UserID = ?", [password_hash, user_id])


def count_users() -> int:
    rows = query_all("SELECT COUNT(*) AS n FROM Users")
    return int(rows[0]["n"]) if rows else 0


def list_users(limit: int = 50) -> list[dict[str, Any]]:
    """列出用户（只给开发者/体检用，绝不暴露密码）。

    注意"只取前 N 行"的写法：SQLite 用 LIMIT、SQL Server 用 TOP，
    所以这里必须交给方言去拼，不能在 SQL 里写死 LIMIT。
    """
    from .dialect import current_dialect

    sql = current_dialect().apply_limit(
        f"SELECT {SAFE_FIELDS} FROM Users ORDER BY UserID", limit
    )
    return query_all(sql)
