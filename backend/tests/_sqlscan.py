#!/usr/bin/env python3
"""共享工具：从 Python 源码里可靠地提取 SQL 语句。

为什么需要单独一个模块：
    静态检查"SQL 里有没有写死某种数据库专有的写法"时，
    最朴素的做法是逐行 grep 或者只看普通字符串常量 —— **两种都会漏**。

    本项目的真实教训：
        `query_all(f"SELECT ... ORDER BY UserID LIMIT {int(limit)}")`

    这句里的 `LIMIT` 只有 SQL Server 不认识（它要用 TOP），
    在本地 SQLite 上永远不会报错，切库时才炸。
    但扫描器**完全没发现它**，因为：
      · 逐行扫描 —— 字符串可能跨多行，且无法区分代码和注释
      · 只看 ast.Constant —— **f-string 在语法树里是 ast.JoinedStr，不是常量**

    所以这里必须同时处理三种形态：
        · 普通字符串常量   "SELECT ..."
        · f-string         f"SELECT ... WHERE X = {var}"
        · 字符串拼接       "SELECT " + cols + " FROM T"

    同时要把**文档字符串排除掉** —— 本项目有多处注释专门在讲解
    "SQLite 写 datetime('now')、SQL Server 写 SYSDATETIME()"，
    如果不排除，这些讲解本身会被误报成"写死了方言函数"。
"""

from __future__ import annotations

import ast
import pathlib
import re

# 判断一段文本"像不像 SQL"
_SQL_HINT = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE)\b", re.IGNORECASE)

# 各种数据库专有、混用就会出事的写法
# 标签 → (正则, 简单说明)
DIALECT_TOKENS: dict[str, tuple[str, str]] = {
    "LIMIT": (r"\bLIMIT\s+\d|\bLIMIT\s*\?", "SQLite/MySQL 写法，SQL Server 要用 TOP"),
    "datetime('now')": (r"datetime\s*\(\s*'now'", "SQLite 专有，SQL Server 用 SYSDATETIME()"),
    "SYSDATETIME()": (r"SYSDATETIME\s*\(", "SQL Server 专有，写在公共 SQL 里换库会报错"),
    "GETDATE()": (r"GETDATE\s*\(", "SQL Server 专有"),
    "AUTOINCREMENT": (r"\bAUTOINCREMENT\b", "SQLite 专有，SQL Server 用 IDENTITY"),
    "IF NOT EXISTS": (r"IF\s+NOT\s+EXISTS", "SQLite/MySQL 语法，SQL Server 不支持建表/建索引用"),
    "|| 拼接": (r"\|\|", "SQLite/Oracle 的字符串拼接，SQL Server 用 +"),
    "strftime()": (r"strftime\s*\(", "SQLite 专有函数"),
    "PRAGMA": (r"\bPRAGMA\b", "SQLite 专有语句"),
    "IFNULL()": (r"\bIFNULL\s*\(", "SQLite 专有，SQL Server 用 ISNULL()"),
    "TOP n": (r"\bTOP\s+\d", "SQL Server 专有，写在公共 SQL 里换库会报错"),
}


def _docstrings(tree: ast.AST) -> set[str]:
    """收集模块/函数/类里的文档字符串原文，用于排除。"""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                found.add(doc)
    return found


def _texts_from(node: ast.AST) -> list[str]:
    """从一个表达式节点里尽可能还原出字符串文本（含 f-string 和拼接）。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]

    if isinstance(node, ast.JoinedStr):
        # f-string：常量片段原样保留，插值部分用占位符代替
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                parts.append(" ? ")
        return ["".join(parts)]

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _texts_from(node.left)
        right = _texts_from(node.right)
        return [a + b for a in left for b in right]

    # 形如 "".join([...]) 的写法也尽量支持
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "join" and node.args:
            sep_texts = _texts_from(node.func.value)
            arg = node.args[0]
            items: list[str] = []
            if isinstance(arg, (ast.List, ast.Tuple)):
                for element in arg.elts:
                    items.extend(_texts_from(element))
            if sep_texts and items:
                return [sep_texts[0].join(items)]

    return []


def sql_strings(path: pathlib.Path | str) -> list[tuple[int, str]]:
    """返回 [(行号, 压平空白的 SQL 文本), ...]，已排除文档字符串。"""
    p = pathlib.Path(path)
    tree = ast.parse(p.read_text(encoding="utf-8"))
    docs = _docstrings(tree)
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        for text in _texts_from(node):
            if text in docs:
                continue
            flat = " ".join(text.split())
            if _SQL_HINT.search(flat):
                out.append((getattr(node, "lineno", 0), flat))
    return out


def scan_dialect_tokens(path: pathlib.Path | str) -> list[tuple[str, int, str, str]]:
    """扫描方言专有写法。

    返回 [(标签, 行号, 说明, SQL 片段), ...]
    """
    hits: list[tuple[str, int, str, str]] = []
    for lineno, sql in sql_strings(path):
        for label, (pattern, explanation) in DIALECT_TOKENS.items():
            if re.search(pattern, sql, re.IGNORECASE):
                hits.append((label, lineno, explanation, sql))
    return hits
