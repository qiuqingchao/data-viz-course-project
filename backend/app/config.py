"""配置中心。

设计原则（很重要）：
1. 代码里 **不写死** 任何密码、Token、数据库连接。
2. 所有可变的配置都放在 backend/.env 这一个文件里（该文件不会被提交/分享给别人）。
3. .env.example 是一份"空白模板"，只写占位符，给别人看或拷到新电脑用。

配置的优先顺序：真实的环境变量 > .env 文件 > 代码里的默认值。
这样部署时可以用环境变量覆盖，而不用改代码。
"""

from __future__ import annotations

import os
from pathlib import Path

# backend/ 目录（本文件在 backend/app/config.py，往上两级）
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


def _load_env_file(path: Path) -> None:
    """一个极简的 .env 读取器（只用 Python 自带能力，不额外装库）。"""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # 已经存在的真实环境变量优先，不被 .env 覆盖
        os.environ.setdefault(key, value)


_load_env_file(ENV_FILE)


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _get_int(key: str, default: int) -> int:
    raw = _get(key)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class Settings:
    """整个后端共用的配置对象。"""

    def __init__(self) -> None:
        # ---------- 基本身份 ----------
        self.app_name: str = _get("APP_NAME", "轻量级课设版数据可视化平台")
        self.app_env: str = _get("APP_ENV", "development")
        self.version: str = "0.1.0"

        # ---------- 后端自身监听地址 ----------
        self.host: str = _get("BACKEND_HOST", "127.0.0.1")
        self.port: int = _get_int("BACKEND_PORT", 8000)

        # ---------- 允许访问后端的前端地址（防止浏览器跨域拦截）----------
        raw_origins = _get(
            "CORS_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173",
        )
        self.cors_origins: list[str] = [o.strip() for o in raw_origins.split(",") if o.strip()]

        # ---------- 数据库：sqlite（本地兜底） 或 mssql（学校 SQL Server）----------
        self.db_mode: str = _get("DB_MODE", "sqlite").lower()
        self.sqlite_path: Path = BASE_DIR / _get("SQLITE_PATH", "data/app.db")

        # 学校 SQL Server 连接信息（密码只放在 .env 里，代码永远读不到明文）
        self.mssql_host: str = _get("MSSQL_HOST", "")
        self.mssql_port: int = _get_int("MSSQL_PORT", 1433)
        self.mssql_database: str = _get("MSSQL_DATABASE", "")
        self.mssql_user: str = _get("MSSQL_USER", "")
        self.mssql_password: str = _get("MSSQL_PASSWORD", "")

        # ---------- 登录令牌的签名密钥（第 3 阶段用）----------
        self.secret_key: str = _get("SECRET_KEY", "")

        # ---------- 内置演示账号 ----------
        # 密码不写在代码里。这里读 .env；为空时由启动程序随机生成并写回 .env。
        self.demo_username: str = _get("DEMO_USERNAME", "demo")
        self.demo_password: str = _get("DEMO_PASSWORD", "")

        # ---------- 上传限制（第 4 阶段用，先在这里集中定义好）----------
        self.max_upload_mb: int = _get_int("MAX_UPLOAD_MB", 5)
        self.max_rows: int = _get_int("MAX_ROWS", 5000)
        self.max_columns: int = _get_int("MAX_COLUMNS", 50)

    # ---------- 给页面看的"人话"描述 ----------
    @property
    def db_mode_label(self) -> str:
        return "本地兜底库（SQLite）" if self.db_mode == "sqlite" else "SQL Server（教学库/远程）"

    @property
    def mssql_configured(self) -> bool:
        """学校数据库信息是否已填全（密码为空就算没配好，密码由使用者自己填）。"""
        return all(
            [
                self.mssql_host,
                self.mssql_database,
                self.mssql_user,
                self.mssql_password,
            ]
        )


settings = Settings()
