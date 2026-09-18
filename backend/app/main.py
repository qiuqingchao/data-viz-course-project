"""后端入口：把"服务员"组装起来并启动。

一条重要原则：**数据库出问题，后端也必须能启动**。
启动时只会尝试"建表 + 建演示账号"，万一数据库连不上，
就把错误记下来、照常提供服务 —— 体检接口会把问题如实报出来，
而不是让整个后端起不来（那样使用者只会看到"网页打不开"，无从排查）。
"""

from __future__ import annotations

import contextlib
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.charts import router as charts_router
from app.api.dashboards import public_router as dashboards_public_router
from app.api.dashboards import router as dashboards_router
from app.api.datasets import router as datasets_router
from app.api.demo import router as demo_router
from app.api.health import router as health_router
from app.config import settings

# 关掉标准输出的"块缓冲"。
# 不改的话，后端被重定向到文件或管道运行时，启动提示会卡在缓冲区里，
# 使用者就看不到"演示账号密码是多少"这类关键信息（曾经真实踩过这个坑）。
try:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
except Exception:  # pragma: no cover - 极少数环境不支持
    pass

# 启动时的准备结果，供体检接口读取
startup_report: dict = {"ok": False, "detail": "启动准备尚未执行"}


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    """启动时建表、建演示账号；启动失败不阻止服务运行。"""
    global startup_report
    try:
        from app.db import bootstrap

        info = bootstrap.bootstrap(verbose=True)
        startup_report = {
            "ok": True,
            "detail": "数据表与演示账号已就绪",
            "schema": info["schema"],
            "demo": {
                "username": info["demo"]["username"],
                "created": info["demo"]["created"],
                # 刻意不回传密码：密码只存在于 .env 和后端控制台
            },
        }
    except Exception as exc:  # noqa: BLE001 - 启动阶段要兜住一切
        startup_report = {
            "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
            "hint": "后端仍可启动，但数据库功能不可用。请检查 backend/.env 的数据库配置。",
        }
        print(f"[启动] ⚠️ 数据库准备失败：{startup_report['detail']}")
        print(f"[启动] {startup_report['hint']}")
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="轻量级课设版数据可视化平台 —— 后端服务",
    lifespan=lifespan,
)

# 允许前端页面（另一个端口）来访问后端，否则浏览器会拦截
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(datasets_router)
app.include_router(charts_router)
app.include_router(dashboards_router)
app.include_router(dashboards_public_router)
app.include_router(demo_router)


@app.get("/", summary="根地址：确认服务已启动")
def root() -> dict:
    return {
        "status": "ok",
        "message": f"{settings.app_name} 后端已启动",
        "docs": "/docs",
        "health": "/api/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
