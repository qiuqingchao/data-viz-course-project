"""SQL 方言：同一套业务代码，要能同时跑在本地 SQLite 和学校 SQL Server 上。

为什么需要这一层？
    两种数据库的写法有真实差异（自增主键、大文本字段、取"刚插入的 ID"）。
    如果把这些差异散落在业务代码里，将来切换数据库就会到处改。
    集中在这里之后，**切换数据库只改配置，不改代码** —— 这正是第 3 阶段的目标。

诚实边界：
    SQLite 这条路径本机已实测跑通；
    SQL Server 这条路径的语句按官方语法编写，但**要等拿到学校库名和密码、
    真正连上去之后才算验证过**。在那之前我不会声称它"已通过测试"。
"""

from __future__ import annotations

import re

from ..config import settings
from .drivers import preferred_driver


class Dialect:
    """方言基类：声明"这里存在差异"，子类负责给出各自写法。"""

    name = "base"
    # 参数占位符风格：sqlite 与 pyodbc 都是 ?，pymssql 是 %s
    paramstyle = "qmark"

    # ---------- 建表相关 ----------
    def autoincrement_pk(self) -> str:
        raise NotImplementedError

    def text(self, length: int | None = None) -> str:
        """文本字段。length 为空表示"长文本"。"""
        raise NotImplementedError

    def datetime_type(self) -> str:
        raise NotImplementedError

    def bit_type(self) -> str:
        """布尔字段。"""
        raise NotImplementedError

    def int_type(self) -> str:
        """整数字段（外键与计数用）。"""
        return "INTEGER"

    def now_expr(self) -> str:
        """当前时间。"""
        raise NotImplementedError

    # ---------- 查询相关 ----------
    def placeholder(self) -> str:
        return "?"

    def apply_limit(self, sql: str, limit: int) -> str:
        """给查询加上"只取前 N 行"。

        两种数据库的写法**完全不同**，写死任何一种换库就报错：
            SQLite      →  SELECT ... ORDER BY X LIMIT 10
            SQL Server  →  SELECT TOP 10 ... ORDER BY X    （TOP 必须紧跟 SELECT）

        这个差异在本地永远测不出来 —— SQLite 对 LIMIT 一路绿灯，
        连上 SQL Server 才报 "Incorrect syntax near 'LIMIT'"。
        """
        n = int(limit)
        if self.name == "sqlite":
            return f"{sql.rstrip()} LIMIT {n}"

        # SQL Server：TOP 必须插在 SELECT（以及可选的 DISTINCT/ALL）之后
        m = re.match(r"(?is)^(\s*SELECT\s+(?:DISTINCT\s+|ALL\s+)?)", sql)
        if not m:
            return sql
        return f"{m.group(1)}TOP {n} " + sql[m.end():]

    def render(self, sql: str) -> str:
        """把统一用 ? 书写的 SQL 转成本方言的写法。

        注意转义顺序（这里很容易写错）：
        必须**先**把字面量的 % 转义成 %%，**再**把 ? 换成 %s。
        反过来的话，刚换出来的 %s 会被二次转义成 %%s，SQL 就废了。
        """
        if self.paramstyle == "qmark":
            return sql
        return sql.replace("%", "%%").replace("?", "%s")

    # ---------- 插入后取回自增 ID ----------
    def post_insert_id_sql(self) -> str | None:
        """取"刚插入那一行的自增 ID"的补充语句；None 表示用 cursor.lastrowid。"""
        return None


class SQLiteDialect(Dialect):
    name = "sqlite"
    paramstyle = "qmark"

    def autoincrement_pk(self) -> str:
        return "INTEGER PRIMARY KEY AUTOINCREMENT"

    def text(self, length: int | None = None) -> str:
        # SQLite 不区分长度，忽略 length
        return "TEXT"

    def datetime_type(self) -> str:
        return "TEXT"

    def bit_type(self) -> str:
        return "INTEGER"

    def int_type(self) -> str:
        return "INTEGER"

    def now_expr(self) -> str:
        # 存成 'YYYY-MM-DD HH:MM:SS' 的文本，排序即时间顺序
        return "datetime('now', 'localtime')"

    def post_insert_id_sql(self) -> str | None:
        return None  # 用 cursor.lastrowid


class MSSQLDialect(Dialect):
    """SQL Server。占位符风格**取决于用哪个驱动**，不能写死。

    pymssql 用 %s，pyodbc 用 ? —— 这个差异如果处理错了，
    每一条带参数的 SQL 都会报错，而且报错信息很难懂。
    """

    name = "mssql"

    def __init__(self) -> None:
        driver = preferred_driver()
        # pymssql 用 pyformat（%s）；pyodbc 用 qmark（?）
        self.paramstyle = "pyformat" if driver == "pymssql" else "qmark"
        self.driver = driver

    def autoincrement_pk(self) -> str:
        return "INT IDENTITY(1,1) PRIMARY KEY"

    def text(self, length: int | None = None) -> str:
        # SQL Server 必须指定长度；长文本用 NVARCHAR(MAX)
        # 必须用 NVARCHAR 而不是 VARCHAR，否则中文会变问号
        return "NVARCHAR(MAX)" if length is None else f"NVARCHAR({length})"

    def datetime_type(self) -> str:
        return "DATETIME2"

    def bit_type(self) -> str:
        return "BIT"

    def int_type(self) -> str:
        return "INT"

    def now_expr(self) -> str:
        return "SYSDATETIME()"

    def post_insert_id_sql(self) -> str | None:
        # 必须起别名：SQL Server 对没有别名的表达式列会返回【空列名】，
        # 驱动拿到空列名时可能直接报错。
        return "SELECT CAST(SCOPE_IDENTITY() AS INT) AS new_id"


def current_dialect() -> Dialect:
    """按配置返回当前使用的方言。"""
    return MSSQLDialect() if settings.db_mode == "mssql" else SQLiteDialect()
