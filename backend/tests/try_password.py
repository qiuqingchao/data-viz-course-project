#!/usr/bin/env python3
"""试密码：验证一个数据库密码对不对，**试对了可以一键存好**。

它和 set_db_config.py 的区别：
    set_db_config.py  是"填写配置"，一次性把库名、用户名、密码都写进 .env
    本工具            是"验证密码"，只试连、不写文件，除非你确认要保存

为什么需要它：
    排查"密码对不对"时，最怕的是每次都要重跑一遍完整配置流程。
    这个工具让你可以安静地试一次密码，看到明确结果。

安全设计：
    · 密码隐藏输入，不回显
    · 密码不写入任何日志、不留在命令历史
    · **试错时不落盘**；只有你确认后才写进 .env

⚠️ 关于账号锁定：
    每次失败都会在服务器上留下一次登录失败记录。如果学校开了
    "密码错误过多锁定账号"，连续试错可能导致账号被临时锁住。
    本工具会统计本次会话的尝试次数，超过 3 次会提醒你先停下来。

运行：
    cd backend && .venv/bin/python tests/try_password.py
"""

from __future__ import annotations

import getpass
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND))

ENV_FILE = BACKEND / ".env"
MAX_SAFE_ATTEMPTS = 3


def decode(exc: Exception) -> str:
    parts = []
    for arg in getattr(exc, "args", ()):
        if isinstance(arg, bytes):
            parts.append(arg.decode("utf-8", errors="replace"))
        else:
            parts.append(str(arg))
    return " | ".join(parts)


def try_login(host: str, port: int, user: str, password: str, database: str):
    import pymssql

    return pymssql.connect(
        server=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8",
        login_timeout=10,
        timeout=15,
        as_dict=True,
    )


def save_password(password: str) -> None:
    """把验证成功的密码写进 .env（复用 set_db_config 里的写入逻辑）。"""
    sys.path.insert(0, str(BACKEND))
    import set_db_config as sdc

    lines = sdc.read_lines(ENV_FILE)
    if ENV_FILE.exists():
        backup = ENV_FILE.with_suffix(ENV_FILE.suffix + ".bak")
        backup.write_text(ENV_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  已备份原文件到 {backup.name}")

    new_lines = sdc.set_values(lines, {"MSSQL_PASSWORD": password})
    ENV_FILE.write_text("\n".join(new_lines).rstrip("\n") + "\n", encoding="utf-8")
    try:
        ENV_FILE.chmod(0o600)
    except Exception:
        pass


def main() -> int:
    from app.config import settings

    host = settings.mssql_host
    port = settings.mssql_port
    user = settings.mssql_user
    database = settings.mssql_database

    print("=" * 72)
    print("试密码 —— 验证数据库密码是否正确")
    print("=" * 72)
    print(f"  服务器   : {host}:{port}")
    print(f"  库名     : {database or '（未填）'}")
    print(f"  用户名   : {user or '（未填）'}")
    print()
    print("说明：密码不会显示、不会存进日志。试错时也不会改动任何文件。")
    print()

    if not all([host, user, database]):
        print("❌ 服务器地址、用户名、库名必须先填好，请先运行 set_db_config.py")
        return 1

    attempts = 0
    while True:
        if attempts >= MAX_SAFE_ATTEMPTS:
            print()
            print("⚠️  本次会话已经试了 %d 次。" % attempts)
            print("    如果学校开了账号锁定策略，继续试可能把账号锁住。")
            try:
                go = input("    仍然要继续吗？输入 yes 回车继续，其它任意键退出：").strip()
            except EOFError:
                go = ""
            if go != "yes":
                print("    已停止。建议先去 Navicat 确认密码，再回来试。")
                return 1

        print("─" * 72)
        try:
            candidate = getpass.getpass("请输入要测试的密码（不显示），直接回车退出：\n> ")
        except EOFError:
            print("（没有输入）")
            return 1
        if not candidate:
            print("已退出。")
            return 0

        attempts += 1
        print(f"\n  正在连接…（本次会话第 {attempts} 次尝试）")

        conn = None
        try:
            conn = try_login(host, port, user, candidate, database)
        except Exception as exc:  # noqa: BLE001
            msg = decode(exc)
            if "18456" in msg or "login failed" in msg.lower():
                print("  ❌ 密码不对（服务器拒绝了这次登录）")
                print()
                print("     请检查：")
                print("       · 字母的大小写（大写/小写很容易记混）")
                print("       · 数字 0 和字母 O、数字 1 和字母 l")
                print("       · 密码里那个特殊符号是什么（@ # . ! * 等）")
                print("       · 密码是不是比 17 位更长（粘贴时可能被截断）")
            elif "4060" in msg or "cannot open database" in msg.lower():
                print("  ✅ 密码是对的！但打不开库，说明是库名的问题：")
                print(f"     库名「{database}」可能拼错了，或这个账号没有被授权访问它。")
                print("     这不是密码问题，请核对 .env 里的 MSSQL_DATABASE。")
                return 2
            else:
                print("  ⚠️  不是密码问题，是别的错误：")
                print(f"     {msg[:300]}")
            print()
            continue
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

        # ── 成功 ──
        print()
        print("  " + "=" * 60)
        print("  ✅ 密码正确！连接成功，库也能打开。")
        print("  " + "=" * 60)

        print()
        try:
            ans = input("要把这个密码保存到 backend/.env 吗？输入 y 回车保存，其它键跳过：").strip().lower()
        except EOFError:
            ans = "n"
        if ans == "y":
            save_password(candidate)
            print()
            print("  ✅ 已保存到 backend/.env（权限 600）")
            print()
            print("  下一步：")
            print("    1. 编辑 backend/.env，把 DB_MODE 改成 mssql")
            print("    2. 重启后端")
            print("    3. 跑隔离测试：PYTHONPATH=. .venv/bin/python tests/test_isolation.py")
        else:
            print("  已跳过，没有改动文件。")
        return 0


if __name__ == "__main__":
    sys.exit(main())
