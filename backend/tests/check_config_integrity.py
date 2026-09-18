#!/usr/bin/env python3
"""配置完整性检查：确认 .env 里的值被程序读到时**一个字符都没被改动**。

为什么需要这个工具：
    `.env` 的解析看起来简单，其实很容易在细节上吃掉字符。最常见的一种写法是

        value.strip().strip('"').strip("'")

    本意是"允许使用者给值加引号"，但它会删掉**首尾所有的引号字符**。
    如果密码本身就以引号开头或结尾，就会被悄悄吃掉 ——
    症状是"我在 Navicat 里明明能连，程序却一直说密码不对"，
    而且怎么查都查不出来。

    这个工具只比对**长度和指纹**，**不打印任何密码内容**，
    所以输出可以直接贴给别人看。

运行：
    cd backend && .venv/bin/python tests/check_config_integrity.py
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND))

ENV_FILE = BACKEND / ".env"

# 需要重点核对的键（值属于敏感信息）
SENSITIVE = ("MSSQL_PASSWORD", "MSSQL_USER", "SECRET_KEY", "DEMO_PASSWORD")
# 顺便一起核对的非敏感键
PLAIN = ("MSSQL_HOST", "MSSQL_PORT", "MSSQL_DATABASE", "DB_MODE", "SQLITE_PATH")

QUOTE_CHARS = (chr(34), chr(39))  # 双引号、单引号

# 这些键的值"被改动"是**故意的**，不算问题。
# SQLITE_PATH 写成相对路径更好移植，程序启动时会把它解析成绝对路径 ——
# 这是预期行为，不是加载器吃字符。不标注的话会被误报成 bug。
NORMALIZED = {
    "SQLITE_PATH": "相对路径被解析成绝对路径（预期行为，便于换机器部署）",
}


def describe_normalization(key: str, raw: str, actual: str) -> str | None:
    """如果这个键的差异属于"预期转换"，返回一句说明；否则返回 None。"""
    if key not in NORMALIZED:
        return None
    if key == "SQLITE_PATH" and actual.endswith(raw) and actual != raw:
        return NORMALIZED[key]
    return None


def raw_values(path: pathlib.Path) -> dict[str, str]:
    """自己解析一遍 .env：原样取等号后面的全部内容，不做任何加工。"""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        out[key.strip()] = value
    return out


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def main() -> int:
    print("=" * 72)
    print("配置完整性检查 —— 确认程序读到的值和文件里写的一模一样")
    print("=" * 72)
    print(f"配置文件：{ENV_FILE}")
    if not ENV_FILE.exists():
        print("文件不存在。")
        return 1
    print()

    raw = raw_values(ENV_FILE)

    # 导入配置模块，拿到"程序实际使用的值"
    from app.config import settings  # noqa: E402

    # 全部统一成字符串再比对：像 SQLITE_PATH 这类字段是 Path 对象，
    # 直接 len() 会抛 TypeError，而且会把"类型不同"误报成"值被改动"。
    actual = {
        "MSSQL_HOST": str(settings.mssql_host),
        "MSSQL_PORT": str(settings.mssql_port),
        "MSSQL_DATABASE": str(settings.mssql_database),
        "MSSQL_USER": str(settings.mssql_user),
        "MSSQL_PASSWORD": str(settings.mssql_password),
        "SECRET_KEY": str(getattr(settings, "secret_key", "")),
        "DEMO_PASSWORD": str(getattr(settings, "demo_password", "")),
        "DB_MODE": str(settings.db_mode),
        "SQLITE_PATH": str(getattr(settings, "sqlite_path", "")),
    }

    problems: list[str] = []

    for key in list(PLAIN) + list(SENSITIVE):
        if key not in raw and key not in actual:
            continue
        r = raw.get(key, "")
        a = actual.get(key, "")
        sensitive = key in SENSITIVE

        if r == a:
            shown = "（敏感值，不显示）" if sensitive else repr(a)
            print(f"  ✅ {key:16} {len(a):>3} 位  指纹 {fingerprint(a)}  {shown}")
            continue

        # 预期的转换（例如路径解析）不算问题
        if (note := describe_normalization(key, r, a)) is not None:
            print(f"  ✅ {key:16} 已按预期转换  {note}")
            print(f"       文件: {r!r}  →  程序使用: {a!r}")
            continue

        # 不一致：这是要抓的 bug
        print(f"  ❌ {key:16} 不一致！")
        print(f"       文件里的值: {len(r)} 位  指纹 {fingerprint(r)}")
        print(f"       程序读到的: {len(a)} 位  指纹 {fingerprint(a)}")
        if not sensitive:
            print(f"       文件: {r!r}")
            print(f"       加载: {a!r}")
        problems.append(key)

        # 判断是怎么被改的
        if r.startswith(a):
            print(f"       → 尾部被吃掉了 {len(r) - len(a)} 个字符")
        elif r.endswith(a):
            print(f"       → 头部被吃掉了 {len(r) - len(a)} 个字符")
        elif a and a in r:
            print("       → 中间有字符被吃掉")
        else:
            print("       → 值被改写（不只是截断）")

        # 定位到具体是什么字符被吃了
        if a and r:
            eaten_head = r[: len(r) - len(a)] if r.endswith(a) else ""
            eaten_tail = r[len(a):] if r.startswith(a) else ""
            for label, eaten in (("开头", eaten_head), ("结尾", eaten_tail)):
                for ch in eaten:
                    if ch in QUOTE_CHARS:
                        print(
                            f"       ★ {label}的引号字符 {ch!r} 被吃掉了 —— "
                            "这就是元凶：加载器里的 .strip(引号) 误删了密码自带的引号"
                        )
                    elif ch.isspace():
                        print(f"       ★ {label}的空白字符被去掉了（这通常是期望行为）")

    print()
    print("─" * 72)
    print("敏感值的首尾字符安全检查（只报是/否，不显示内容）")
    for key in SENSITIVE:
        v = raw.get(key, "")
        if not v:
            print(f"  {key:16} 为空，跳过")
            continue
        flags = []
        if v[0] in QUOTE_CHARS:
            flags.append(f"开头是引号 {v[0]!r}")
        if v[-1] in QUOTE_CHARS:
            flags.append(f"结尾是引号 {v[-1]!r}")
        if v[0].isspace():
            flags.append("开头是空白")
        if v[-1].isspace():
            flags.append("结尾是空白")
        if v != v.strip():
            flags.append("首尾有空白（会被去掉）")
        print(f"  {key:16} " + ("；".join(flags) if flags else "首尾字符安全 ✅"))

    print()
    print("─" * 72)
    if problems:
        print(f"❌ 发现 {len(problems)} 个键的值被加载器改动了：{', '.join(problems)}")
        print("   这会导致『文件里看着对、程序实际用错值』，必须修。")
        return 1
    print("✅ 全部一致：程序读到的值和 .env 里写的一模一样，没有任何字符被吃掉。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
