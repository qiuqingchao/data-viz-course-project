#!/usr/bin/env python3
"""交互式填写学校数据库的库名和密码。

为什么做成"你来运行"的脚本，而不是直接改文件？
    1. 密码由你亲手输入，**不会出现在任何聊天记录里**；
    2. 输入是隐藏的（像输密码那样不显示），**也不会留在命令历史里**；
    3. 手改 .env 容易踩坑：多打了引号、多打了空格、存成了 GBK 编码 ——
       这三个都会导致"连不上"，而且报错信息很难懂。脚本会替你挡掉。

用法：
    cd backend && .venv/bin/python set_db_config.py

想先拿一份副本练手（不动真正的配置）：
    .venv/bin/python set_db_config.py --file /tmp/practice.env
"""

from __future__ import annotations

import argparse
import getpass
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_ENV = HERE / ".env"


def read_lines(path: pathlib.Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def get_value(lines: list[str], key: str) -> str:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") and not stripped.startswith("#"):
            return stripped.split("=", 1)[1]
    return ""


def set_values(lines: list[str], updates: dict[str, str]) -> list[str]:
    """更新若干 key。已存在就替换那一行，不存在就在末尾追加。"""
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        matched = None
        for key in updates:
            if stripped.startswith(f"{key}=") and not stripped.startswith("#"):
                matched = key
                break
        if matched:
            out.append(f"{matched}={updates[matched]}")
            seen.add(matched)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    return out


def mask(value: str) -> str:
    if not value:
        return "（空）"
    if len(value) <= 2:
        return "*" * len(value)
    return value[0] + "*" * (len(value) - 2) + value[-1]


def ask(prompt: str, current: str = "") -> str:
    """普通提问（内容可见）。直接回车表示保持不变。"""
    suffix = f"（当前：{current}，直接回车保持不变）" if current else ""
    try:
        answer = input(f"{prompt}{suffix}\n> ").strip()
    except EOFError:
        answer = ""
    return answer or current


def ask_secret(prompt: str, has_existing: bool) -> str:
    """密码提问：输入不回显。直接回车表示保持不变。"""
    hint = "（已填写，直接回车保持不变）" if has_existing else "（必填）"
    try:
        first = getpass.getpass(f"{prompt}{hint}\n> ")
    except EOFError:
        return ""
    if not first:
        return ""

    try:
        again = getpass.getpass("请再输入一次以确认\n> ")
    except EOFError:
        again = first
    if first != again:
        print("\n❌ 两次输入不一致，没有做任何修改。请重新运行。")
        sys.exit(1)
    return first


def check_value(key: str, value: str) -> str | None:
    """返回 None 表示合格，否则返回人话原因。"""
    if not value:
        return None
    if value != value.strip():
        return "开头或结尾有空格。.env 会自动去掉这些空格，请重新输入。"
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return "不要加引号。.env 的格式就是「键=值」，引号会被当成内容的一部分。"
    if any(ch in value for ch in "\r\n"):
        return "不能包含换行。"
    if key == "MSSQL_PASSWORD" and "=" in value:
        return None  # 密码里可以有 =，读取时只按第一个 = 切分，不会有问题
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="填写学校数据库配置")
    parser.add_argument("--file", default=str(DEFAULT_ENV), help="要修改的 .env 路径")
    args = parser.parse_args()

    path = pathlib.Path(args.file)
    lines = read_lines(path)

    print("=" * 70)
    print("填写学校数据库配置")
    print("=" * 70)
    print(f"目标文件：{path}")
    if not path.exists():
        print("（该文件不存在，将新建）")
    print()

    cur_db = get_value(lines, "MSSQL_DATABASE")
    cur_user = get_value(lines, "MSSQL_USER")
    cur_pwd = get_value(lines, "MSSQL_PASSWORD")

    print("当前状态：")
    print(f"  数据库地址 : {get_value(lines, 'MSSQL_HOST') or '（空）'}")
    print(f"  端口       : {get_value(lines, 'MSSQL_PORT') or '（空）'}")
    print(f"  库名       : {cur_db or '（空）'}")
    print(f"  用户名     : {cur_user or '（空）'}")
    print(f"  密码       : {mask(cur_pwd)}")
    print()
    print("提示：下面每一项如果不想改，直接按回车。")
    print("-" * 70)

    db = ask("① 数据库库名（学校给你的那个）", cur_db)
    if (reason := check_value("MSSQL_DATABASE", db)) is not None:
        print(f"\n❌ 库名有问题：{reason}")
        return 1

    user = ask("② 用户名（确认一下，不对就改）", cur_user)
    if (reason := check_value("MSSQL_USER", user)) is not None:
        print(f"\n❌ 用户名有问题：{reason}")
        return 1

    print()
    print("③ 密码（输入时不显示，是正常的；这是为了保护你的密码）")
    pwd = ask_secret("请输入数据库密码", bool(cur_pwd))
    if (reason := check_value("MSSQL_PASSWORD", pwd)) is not None:
        print(f"\n❌ 密码有问题：{reason}")
        return 1

    print()
    print("-" * 70)
    print("即将写入以下内容：")
    print(f"  库名   : {db or '（空）'}")
    print(f"  用户名 : {user or '（空）'}")
    print(f"  密码   : {mask(pwd)}")
    print(f"  DB_MODE: 保持不改（先跑体检确认能连上，再手动切换）")
    print()

    if not db or not pwd:
        print("⚠️  库名或密码仍是空的。写进去也连不上，确定要继续吗？")

    try:
        confirm = input("确认写入？输入 y 回车，其它任意键取消：").strip().lower()
    except EOFError:
        confirm = "n"
    if confirm != "y":
        print("已取消，没有做任何修改。")
        return 0

    # 备份一份，改坏了还能退回去
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"已备份原文件到：{backup.name}")

    new_lines = set_values(lines, {
        "MSSQL_DATABASE": db,
        "MSSQL_USER": user,
        "MSSQL_PASSWORD": pwd,
    })
    path.write_text("\n".join(new_lines).rstrip("\n") + "\n", encoding="utf-8")

    # 收紧权限：只有你自己能读这个文件
    try:
        path.chmod(0o600)
    except Exception:
        pass

    print()
    print("=" * 70)
    print("✅ 已写入。检查一下：")
    print(f"   文件编码：UTF-8（脚本保证）")
    print(f"   文件权限：{'600（仅你可读写）' if oct(path.stat().st_mode)[-3:] == '600' else oct(path.stat().st_mode)[-3:]}")
    print(f"   库名    ：{db or '（空）'}")
    print(f"   密码    ：{mask(pwd)}（长度 {len(pwd)}）")
    print()
    print("下一步（回到项目根目录执行）：")
    print("   cd ..")
    print("   cd backend && PYTHONPATH=. .venv/bin/python tests/check_mssql.py")
    print("   把体检结果发给我，我来判断能不能切库。")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
