"""启动时的准备工作：建表 + 创建内置演示账号。

为什么要有这一步？
    第一次在新电脑（或学校的数据库）上启动时，里面什么表都没有。
    让"启动"顺手把该建的建好、该有的演示账号建好，
    使用者就不需要手动去数据库里敲 SQL —— 少一个出错的机会。

关于演示账号的密码（重要）：
    代码里**不写死任何密码**。规则是：
      1. 先看 backend/.env 里的 DEMO_PASSWORD；
      2. 没配就**随机生成一个强密码**，写回 .env，并在控制台大方地打印出来。
    这样既不违反"不硬编码密码"，使用者又能随时在 .env 里查到它、换成自己想要的。
"""

from __future__ import annotations

import secrets
import string

from ..config import ENV_FILE, settings
from ..security.passwords import hash_password
from . import users
from .connection import execute, index_exists, table_exists
from .schema import index_definitions, table_definitions

DEMO_USERNAME = "demo"
DEMO_DISPLAY_NAME = "演示账号"


# --------------------------------------------------------------- 建表


def ensure_schema() -> dict:
    """建好缺的表和索引。已存在的跳过，不会破坏已有数据。"""
    created_tables: list[str] = []
    created_indexes: list[str] = []

    for name, sql in table_definitions():
        if not table_exists(name):
            execute(sql)
            created_tables.append(name)

    for name, sql in index_definitions():
        if not index_exists(name):
            execute(sql)
            created_indexes.append(name)

    return {"created_tables": created_tables, "created_indexes": created_indexes}


# --------------------------------------------------- .env 的读写（仅演示密码）


def _read_env_lines() -> list[str]:
    if not ENV_FILE.exists():
        return []
    return ENV_FILE.read_text(encoding="utf-8").splitlines()


def _write_env_value(key: str, value: str) -> None:
    """把某个配置项写回 .env（只用于自动生成演示密码这一种情况）。"""
    lines = _read_env_lines()
    out: list[str] = []
    replaced = False
    for line in lines:
        if line.strip().startswith(f"{key}=") and not line.strip().startswith("#"):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")


def _generate_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def ensure_demo_user() -> dict:
    """确保演示账号存在。返回一份"给你看"的说明。"""
    username = (settings.demo_username or DEMO_USERNAME).strip() or DEMO_USERNAME

    existing = users.find_by_username(username)
    if existing:
        return {
            "username": username,
            "created": False,
            "password": None,
            "message": f"演示账号「{username}」已存在，未改动。",
        }

    password = settings.demo_password.strip()
    generated = False
    if not password:
        password = _generate_password()
        generated = True
        # 写回 .env，方便使用者随时查看或修改
        _write_env_value("DEMO_USERNAME", username)
        _write_env_value("DEMO_PASSWORD", password)

    users.create_user(
        username=username,
        password_hash=hash_password(password),
        display_name=DEMO_DISPLAY_NAME,
        role="demo",
    )
    msg = f"已创建演示账号「{username}」。"
    if generated:
        msg += "密码是随机生成的，已写入 backend/.env 的 DEMO_PASSWORD。"
    return {"username": username, "created": True, "password": password, "message": msg}


# ------------------------------------------------------------- 总入口


def bootstrap(verbose: bool = True) -> dict:
    schema_info = ensure_schema()
    demo_info = ensure_demo_user()

    if verbose:
        if schema_info["created_tables"]:
            print(f"[启动] 新建数据表：{', '.join(schema_info['created_tables'])}")
        if schema_info["created_indexes"]:
            print(f"[启动] 新建索引：{', '.join(schema_info['created_indexes'])}")
        if not schema_info["created_tables"] and not schema_info["created_indexes"]:
            print("[启动] 数据表已就绪")
        print(f"[启动] {demo_info['message']}")
        if demo_info.get("password"):
            # 只在"新建"时打印一次；密码同时已存进 .env
            print(f"[启动] 演示账号登录信息 → 用户名 {demo_info['username']} / 密码 {demo_info['password']}")

    return {"schema": schema_info, "demo": demo_info}
