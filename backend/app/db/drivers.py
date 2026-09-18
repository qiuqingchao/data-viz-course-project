"""数据库驱动探测。

连 SQL Server 有两条路，各有利弊：

  pymssql  —— 安装包**自带**底层库（FreeTDS 等），一条 pip 命令搞定，
              **不需要系统权限、不需要 sudo**。本项目首选。
              参数占位符用 `%s`。

  pyodbc   —— 微软官方推荐的路线，但需要额外安装系统级 ODBC 驱动
              （Linux 上要装 msodbcsql18，需要 sudo），体积也大得多。
              参数占位符用 `?`。

两条路都支持，但优先 pymssql —— 对使用者来说少一道门槛。
"""

from __future__ import annotations


def available_drivers() -> list[str]:
    """返回当前环境里真正装了的驱动名（按优先级排序）。"""
    found: list[str] = []
    for name in ("pymssql", "pyodbc"):
        try:
            __import__(name)
            found.append(name)
        except ImportError:
            continue
    return found


def preferred_driver() -> str | None:
    drivers = available_drivers()
    return drivers[0] if drivers else None


def driver_hint() -> str:
    """给使用者看的一句话说明（体检接口和报错信息都会用到）。"""
    drivers = available_drivers()
    if not drivers:
        return "没有安装任何 SQL Server 驱动，需要先执行 pip install pymssql"
    if drivers[0] == "pymssql":
        return f"已安装 pymssql {_version('pymssql')}（自带底层库，无需系统权限）"
    return f"已安装 {drivers[0]}（需要系统里已配好 ODBC 驱动）"


def _version(module_name: str) -> str:
    try:
        mod = __import__(module_name)
        return str(getattr(mod, "__version__", "?"))
    except Exception:
        return "?"
