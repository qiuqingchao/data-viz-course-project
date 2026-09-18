"""数据库连接与统一查询接口。

三条规矩：
  1. **每次用连接现开现关**。FastAPI 会把同步接口丢到线程池里跑，
     共享一个连接会出并发问题；课设的访问量很小，现开现关最省心也最安全。
  2. 上层只看到 query_all / query_one / execute 三个函数，
     不需要知道底下是 SQLite 还是 SQL Server。
  3. 所有 SQL 里的参数一律用 `?` 占位、参数走列表传参，
     **绝不把用户输入拼进 SQL 字符串**（这是防 SQL 注入的根本办法）。
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from ..config import settings
from .dialect import Dialect, current_dialect
from .drivers import driver_hint, preferred_driver

# ---------------------------------------------------------------- 连接实现


def _connect_sqlite() -> Any:
    path = settings.sqlite_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    # 外键约束默认是关的，必须手动打开，否则外键形同虚设
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL 模式：读写不互相阻塞，本地开发更顺
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _connect_mssql() -> Any:
    """连接学校 SQL Server。

    优先用 pymssql —— 它自带底层库，不需要系统装 ODBC 驱动，也就不需要管理员权限。
    没有 pymssql 时才退回 pyodbc。
    """
    driver = preferred_driver()

    if driver == "pymssql":
        import pymssql

        return pymssql.connect(
            server=settings.mssql_host,
            port=settings.mssql_port,
            user=settings.mssql_user,
            password=settings.mssql_password,  # 来自 .env，代码里没有明文
            database=settings.mssql_database,
            # 必须显式指定 utf8，否则中文会变问号或乱码
            charset="utf8",
            login_timeout=10,
            timeout=15,
            # 刻意【不】使用 as_dict=True：
            # pymssql 在 as_dict=True 下，只要结果里有一列没有别名
            # （SQL Server 对 SELECT 1、COUNT(*)、CAST(...) 这类表达式会返回空列名），
            # 就会直接抛 ColumnsWithoutNamesError，整个功能不可用。
            # 统一走 _rows_to_dicts()+cursor.description 更稳，也让三个驱动行为一致。
        )

    if driver == "pyodbc":
        import pyodbc

        installed = [d for d in pyodbc.drivers() if "SQL Server" in d]
        if not installed:
            raise RuntimeError(
                "装了 pyodbc，但系统里没有 SQL Server 的 ODBC 驱动。"
                "建议改用 pymssql（pip install pymssql，不需要系统权限）："
                "两者只能留一个，装好 pymssql 后会自动优先使用它。"
            )
        conn_str = (
            f"DRIVER={{{sorted(installed)[-1]}}};"
            f"SERVER={settings.mssql_host},{settings.mssql_port};"
            f"DATABASE={settings.mssql_database};"
            f"UID={settings.mssql_user};"
            f"PWD={settings.mssql_password};"
            "TrustServerCertificate=yes;"
            "Encrypt=no;"
        )
        return pyodbc.connect(conn_str, timeout=10, autocommit=False)

    raise RuntimeError(
        "没有安装任何 SQL Server 驱动，无法连接学校数据库。"
        "解决办法（不需要管理员权限）：pip install pymssql"
    )


def _connect() -> Any:
    return _connect_mssql() if settings.db_mode == "mssql" else _connect_sqlite()


@contextmanager
def get_connection() -> Iterator[Any]:
    """拿一个连接，正常结束就提交，出错就回滚，最后一定关掉。"""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ------------------------------------------------------- 行 → 字典的转换


def _rows_to_dicts(cursor: Any, rows: list[Any]) -> list[dict]:
    """把各家驱动返回的行统一成字典。

    三种情况都要处理：
      · SQLite      → sqlite3.Row
      · pymssql     → 元组（我们刻意没用 as_dict=True，见上面的说明）
      · pyodbc/其它 → 元组，需要靠 cursor.description 拼列名
    """
    if not rows:
        return []
    first = rows[0]
    if isinstance(first, (dict, sqlite3.Row)):
        return [dict(r) for r in rows]
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, r)) for r in rows]


# 判断一条语句是不是 INSERT（决定要不要去取自增 ID）
_INSERT_RE = re.compile(r"^\s*INSERT\s", re.IGNORECASE)


# ------------------------------------------------------------ 对外接口


def query_all(sql: str, params: list[Any] | None = None, dialect: Dialect | None = None) -> list[dict]:
    d = dialect or current_dialect()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(d.render(sql), params or [])
        return _rows_to_dicts(cur, cur.fetchall())


def query_one(sql: str, params: list[Any] | None = None, dialect: Dialect | None = None) -> dict | None:
    rows = query_all(sql, params, dialect)
    return rows[0] if rows else None


def execute(sql: str, params: list[Any] | None = None, dialect: Dialect | None = None) -> int:
    """执行写操作。

    返回值有两种含义（看语句类型）：
        INSERT          → 新插入那一行的自增 ID
        UPDATE / DELETE → 实际影响了多少行

    这里有两个**只在 SQL Server 上才会暴露**的坑，都踩过：

    1) 无条件去取自增 ID。对 UPDATE / DELETE 也执行一条
       `SELECT SCOPE_IDENTITY()`，那条 SELECT 会把 cur.rowcount 覆盖成 -1，
       于是"影响了几行"就永远返回 -1。SQLite 不会中招，
       因为它用游标的 lastrowid、不需要额外查询 —— 所以本地怎么测都正常。

    2) 分不清"影响 0 行"和"不知道"。调用方靠 `affected == 0` 判断
       "这条数据不是你的 / 不存在"，返回值必须是精确的 0。

    修法是：先把 rowcount 存下来，并且只在 INSERT 时才去问自增 ID。
    """
    d = dialect or current_dialect()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(d.render(sql), params or [])

        # 先记下这条语句自己影响了几行 —— 后面的额外查询会覆盖 rowcount
        affected = cur.rowcount

        # 只有 INSERT 才需要自增 ID
        if _INSERT_RE.match(sql):
            tail = d.post_insert_id_sql()
            if tail:
                cur.execute(tail)
                row = cur.fetchone()
                if row is not None:
                    value = next(iter(row.values())) if isinstance(row, dict) else row[0]
                    new_id = int(value) if value is not None else 0
                    if new_id:
                        return new_id
            lastrowid = getattr(cur, "lastrowid", None)
            if lastrowid:
                return int(lastrowid)

        return affected


def execute_many(sql: str, seq_params: list[list[Any]], dialect: Dialect | None = None) -> int:
    """批量执行，返回累计影响行数。

    这里没有再执行额外查询，所以 rowcount 是准的 ——
    但仍要留意：将来若在这里加"取 ID"之类的额外查询，会重蹈 execute() 的覆辙。
    """
    d = dialect or current_dialect()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.executemany(d.render(sql), seq_params)
        return cur.rowcount


def now_sql() -> str:
    """当前时间的 SQL 写法。

    为什么需要它：SQLite 写 datetime('now')，SQL Server 写 SYSDATETIME()。
    在 UPDATE 语句里写死任何一种，切换数据库时都会直接报错。
    所有"更新时顺便刷新时间"的地方都必须走这里。
    """
    return current_dialect().now_expr()


# ------------------------------------------------- 建表 / 表是否存在的判断


def table_exists(name: str) -> bool:
    d = current_dialect()
    if d.name == "sqlite":
        row = query_one("SELECT name FROM sqlite_master WHERE type='table' AND name=?", [name])
    else:
        row = query_one(
            "SELECT TABLE_NAME AS name FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?", [name]
        )
    return row is not None


def index_exists(name: str) -> bool:
    d = current_dialect()
    if d.name == "sqlite":
        row = query_one("SELECT name FROM sqlite_master WHERE type='index' AND name=?", [name])
    else:
        row = query_one("SELECT name FROM sys.indexes WHERE name = ?", [name])
    return row is not None


def ping() -> tuple[bool, str]:
    """试探数据库是否真的能用（给体检接口用）。"""
    try:
        d = current_dialect()
        row = query_one("SELECT 1 AS ok")
        if row and int(next(iter(row.values()))) == 1:
            suffix = f"（驱动 {getattr(d, 'driver', None) or '内置'}）" if d.name == "mssql" else ""
            return True, f"{d.name} 连接正常{suffix}"
        return False, "数据库返回了意外的结果"
    except Exception as exc:  # pragma: no cover - 依赖真实环境
        return False, f"{type(exc).__name__}: {exc}"
