#!/usr/bin/env python3
"""表结构可移植性测试：保证建表语句在 SQL Server 上真的能跑。

为什么需要这个测试：
    SQLite 对标识符极其宽容，几乎什么名字都收；SQL Server 严格得多。
    于是就有了一类**只会在连真库时才爆炸**的问题：

        RowCount   →  ROWCOUNT 是 SQL Server 保留字
                      CREATE TABLE 直接报 "Incorrect syntax near the keyword"

    这个坑在本项目真实发生过：本地 SQLite 一路绿灯，
    切到学校数据库启动时才炸。而且它出现在**启动阶段**，
    表现为"整个后端不可用"，排查成本很高。

    所以这里把"逐字验证"固化成测试，以后改表结构会自动拦下来。

验证方式（优先用第一种，更可信）：
    1. 真实探测：连上 SQL Server，把每个标识符**不带引号**地拿去建临时表
       （临时表用完自动消失，不会在你的库里留下任何东西）
    2. 离线兜底：没配数据库时，退回内置的 T-SQL 保留字表做比对

运行：
    cd backend && PYTHONPATH=. .venv/bin/python tests/test_schema_portability.py
"""

from __future__ import annotations

import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND))

from app.db.dialect import MSSQLDialect, SQLiteDialect  # noqa: E402
from app.db.schema import index_definitions, table_definitions  # noqa: E402

# T-SQL 保留字（离线兜底用，来源：Microsoft 官方保留关键字列表，节选常用部分）
TSQL_RESERVED = {
    "ADD", "ALL", "ALTER", "AND", "ANY", "AS", "ASC", "AUTHORIZATION", "BACKUP",
    "BEGIN", "BETWEEN", "BREAK", "BROWSE", "BULK", "BY", "CASCADE", "CASE",
    "CHECK", "CHECKPOINT", "CLOSE", "CLUSTERED", "COALESCE", "COLLATE", "COLUMN",
    "COMMIT", "COMPUTE", "CONSTRAINT", "CONTAINS", "CONTAINSTABLE", "CONTINUE",
    "CONVERT", "CREATE", "CROSS", "CURRENT", "CURRENT_DATE", "CURRENT_TIME",
    "CURRENT_TIMESTAMP", "CURRENT_USER", "CURSOR", "DATABASE", "DBCC",
    "DEALLOCATE", "DECLARE", "DEFAULT", "DELETE", "DENY", "DESC", "DISK",
    "DISTINCT", "DISTRIBUTED", "DOUBLE", "DROP", "DUMP", "ELSE", "END", "ERRLVL",
    "ESCAPE", "EXCEPT", "EXEC", "EXECUTE", "EXISTS", "EXIT", "EXTERNAL", "FETCH",
    "FILE", "FILLFACTOR", "FOR", "FOREIGN", "FREETEXT", "FREETEXTTABLE", "FROM",
    "FULL", "FUNCTION", "GOTO", "GRANT", "GROUP", "HAVING", "HOLDLOCK", "IDENTITY",
    "IDENTITY_INSERT", "IDENTITYCOL", "IF", "IN", "INDEX", "INNER", "INSERT",
    "INTERSECT", "INTO", "IS", "JOIN", "KEY", "KILL", "LEFT", "LIKE", "LINENO",
    "LOAD", "MERGE", "NATIONAL", "NOCHECK", "NONCLUSTERED", "NOT", "NULL",
    "NULLIF", "OF", "OFF", "OFFSETS", "ON", "OPEN", "OPENDATASOURCE",
    "OPENQUERY", "OPENROWSET", "OPENXML", "OPTION", "OR", "ORDER", "OUTER",
    "OVER", "PERCENT", "PIVOT", "PLAN", "PRECISION", "PRIMARY", "PRINT", "PROC",
    "PROCEDURE", "PUBLIC", "RAISERROR", "READ", "READTEXT", "RECONFIGURE",
    "REFERENCES", "REPLICATION", "RESTORE", "RESTRICT", "RETURN", "REVERT",
    "REVOKE", "RIGHT", "ROLLBACK", "ROWCOUNT", "ROWGUIDCOL", "RULE", "SAVE",
    "SCHEMA", "SECURITYAUDIT", "SELECT", "SEMANTICKEYPHRASETABLE",
    "SEMANTICSIMILARITYDETAILSTABLE", "SEMANTICSIMILARITYTABLE", "SESSION_USER",
    "SET", "SETUSER", "SHUTDOWN", "SOME", "STATISTICS", "SYSTEM_USER", "TABLE",
    "TABLESAMPLE", "TEXTSIZE", "THEN", "TO", "TOP", "TRAN", "TRANSACTION",
    "TRIGGER", "TRUNCATE", "TRY_CONVERT", "TSEQUAL", "UNION", "UNIQUE",
    "UNPIVOT", "UPDATE", "UPDATETEXT", "USE", "USER", "VALUES", "VARYING",
    "VIEW", "WAITFOR", "WHEN", "WHERE", "WHILE", "WITH", "WITHIN GROUP",
    "WRITETEXT",
}

PASS, FAIL, WARN, SKIP = "✅", "❌", "⚠️ ", "⏭️ "

# 从建表语句里抽出所有标识符
COLUMN_RE = re.compile(
    r"^\s{4,}([A-Za-z_][A-Za-z0-9_]*)\s+(?:INT|NVARCHAR|DATETIME2|BIT|INTEGER)",
    re.MULTILINE,
)


def collect_identifiers() -> dict[str, list[str]]:
    """收集所有表名和列名，并标出它们各自属于哪张表。"""
    result: dict[str, list[str]] = {}
    for table_name, sql in table_definitions(MSSQLDialect()):
        cols = COLUMN_RE.findall(sql)
        result[table_name] = cols
    return result


def check_offline(idents: dict[str, list[str]]) -> list[str]:
    """离线兜底：拿内置保留字表比对。"""
    problems = []
    for table, cols in idents.items():
        for name in [table] + cols:
            if name.upper() in TSQL_RESERVED:
                problems.append(f"{table}.{name}")
    return problems


def check_live(idents: dict[str, list[str]]) -> tuple[list[str], str]:
    """连真实 SQL Server 逐字验证（用临时表，不污染数据库）。"""
    import pymssql

    from app.config import settings

    conn = pymssql.connect(
        server=settings.mssql_host,
        port=settings.mssql_port,
        user=settings.mssql_user,
        password=settings.mssql_password,
        database=settings.mssql_database,
        charset="utf8",
        login_timeout=10,
        timeout=20,
    )
    cur = conn.cursor()
    problems: list[str] = []
    checked = 0
    note = ""

    try:
        idx = 0
        for table, cols in idents.items():
            for name in [table] + cols:
                idx += 1
                tmp = f"#probe{idx}"
                try:
                    # 关键：**不加方括号**，这才是真实建表时的样子
                    cur.execute(f"CREATE TABLE {tmp} ({name} INT)")
                    cur.execute(f"DROP TABLE {tmp}")
                    checked += 1
                except Exception as exc:  # noqa: BLE001
                    msg = " ".join(
                        a.decode("utf-8", "replace") if isinstance(a, bytes) else str(a)
                        for a in getattr(exc, "args", ())
                    )
                    if "156" in msg or "syntax" in msg.lower():
                        problems.append(f"{table}.{name}")
                    else:
                        note = f"（{name} 检测时遇到非语法错误：{msg[:60]}）"
                    try:
                        conn.rollback()
                    except Exception:
                        pass

        # 顺带确认整段建表语句能被 SQL Server 解析
        try:
            cur.execute("SET NOEXEC ON")
            for _, sql in table_definitions(MSSQLDialect()):
                cur.execute(sql)
            cur.execute("SET NOEXEC OFF")
            note += " 建表语句整体可通过 SQL Server 语法解析"
        except Exception as exc:  # noqa: BLE001
            try:
                cur.execute("SET NOEXEC OFF")
            except Exception:
                pass
            problems.append(f"整套建表语句：{str(exc)[:120]}")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return problems, f"真实探测了 {checked} 个标识符。{note}"


def main() -> int:
    print("=" * 74)
    print("表结构可移植性测试（SQL Server 保留字 / 语法）")
    print("=" * 74)

    idents = collect_identifiers()
    total = sum(len(c) for c in idents.values()) + len(idents)
    print(f"\n共 {len(idents)} 张表、{total} 个标识符待检查：")
    for table, cols in idents.items():
        print(f"  · {table} ({len(cols)} 列)")

    # ── 1. 离线检查 ──
    print("\n【1】离线检查（内置 T-SQL 保留字表）")
    offline = check_offline(idents)
    if offline:
        for item in offline:
            print(f"  {FAIL} {item} 撞了 SQL Server 保留字")
    else:
        print(f"  {PASS} 没有标识符撞上保留字")

    # ── 2. 真实探测 ──
    print("\n【2】真实数据库逐字探测")
    live: list[str] = []
    from app.config import settings

    if settings.db_mode != "mssql" or not settings.mssql_configured:
        print(f"  {SKIP} 当前不是 SQL Server 模式或配置不全，跳过真实探测")
        print("       （离线检查已覆盖保留字问题）")
    else:
        try:
            live, note = check_live(idents)
            if live:
                for item in live:
                    print(f"  {FAIL} {item}")
            else:
                print(f"  {PASS} 全部通过。{note}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {WARN} 连不上数据库，跳过真实探测（不影响离线结论）")
            print(f"       {type(exc).__name__}: {str(exc)[:140]}")

    # ── 3. 两种方言的建表语句都要能生成 ──
    print("\n【3】两种数据库的建表语句都能正常生成")
    ok = True
    for label, d in (("SQLite", SQLiteDialect()), ("SQL Server", MSSQLDialect())):
        try:
            tables = table_definitions(d)
            indexes = index_definitions(d)
            joined = " ".join(sql for _, sql in tables)
            assert "CREATE TABLE" in joined, "建表语句缺失"
            print(f"  {PASS} {label}：{len(tables)} 张表 + {len(indexes)} 个索引")
        except Exception as exc:  # noqa: BLE001
            print(f"  {FAIL} {label}：{exc}")
            ok = False

    # ── 4. 禁止出现在建表语句里的写法 ──
    print("\n【4】静态检查：不允许出现 SQL Server 不认识的写法")
    bad_patterns = [
        (r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS", "CREATE TABLE IF NOT EXISTS"),
        (r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS", "CREATE INDEX IF NOT EXISTS"),
        (r"AUTOINCREMENT", "AUTOINCREMENT 关键字"),
    ]
    mssql_sql = "\n".join(sql for _, sql in table_definitions(MSSQLDialect()))
    mssql_sql += "\n".join(sql for _, sql in index_definitions(MSSQLDialect()))
    found = False
    for pattern, label in bad_patterns:
        if re.search(pattern, mssql_sql, re.IGNORECASE):
            print(f"  {FAIL} SQL Server 版本里出现了 {label}")
            found = True
    if not found:
        print(f"  {PASS} 没有 SQLite 专有写法混进 SQL Server 语句")

    # ── 结论 ──
    problems = offline + live
    print("\n" + "=" * 74)
    if problems:
        print(f"❌ 发现 {len(problems)} 个问题：")
        for p in problems:
            print(f"   · {p}")
        print("\n   修法：给它换个不撞保留字的名字（推荐），")
        print("         或者在整个项目里都用方括号包起来（容易漏，不推荐）。")
        return 1
    print("✅ 表结构可移植性检查通过。")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
