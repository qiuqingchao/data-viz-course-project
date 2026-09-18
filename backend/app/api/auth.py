"""账号接口：注册、登录、查看自己、自己的数据概况。

安全上做了这几件事（都不是"可选"的）：
  1. 密码用 scrypt 加密后入库，明文不落盘、不进日志；
  2. 登录成功签发带签名和有效期的令牌；
  3. **登录失败次数限制**：连续输错会被短暂锁定，挡住暴力猜密码；
  4. 登录失败时**不透露**"是用户名错了还是密码错了" —— 两个都回同一句话，
     否则等于帮攻击者确认"这个用户名存在"。
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..db import data, users
from ..security.passwords import check_password_strength, check_username, hash_password, verify_password
from ..security.tokens import DEFAULT_TTL_SECONDS, create_token
from .deps import current_user, user_id_of

router = APIRouter(prefix="/api/auth", tags=["账号"])


# ------------------------------------------------------------ 请求体定义

class RegisterBody(BaseModel):
    username: str = Field(..., description="用户名，3~32 位")
    password: str = Field(..., description="密码，至少 6 位")
    display_name: str | None = Field(default=None, description="显示名，可留空")


class LoginBody(BaseModel):
    username: str
    password: str


# ----------------------------------------------- 登录失败次数限制（防猜密码）

_MAX_FAILS = 5
_LOCK_SECONDS = 60
_fail_records: dict[str, list] = {}  # 用户名 → [失败次数, 最近一次失败时间]


def _is_locked(username: str) -> int:
    """返回还需等待的秒数；0 表示未锁定。"""
    rec = _fail_records.get(username.lower())
    if not rec:
        return 0
    fails, last = rec
    if fails < _MAX_FAILS:
        return 0
    remain = int(_LOCK_SECONDS - (time.time() - last))
    if remain <= 0:
        _fail_records.pop(username.lower(), None)
        return 0
    return remain


def _record_fail(username: str) -> None:
    key = username.lower()
    fails, _ = _fail_records.get(key, [0, 0.0])
    _fail_records[key] = [fails + 1, time.time()]


def _clear_fail(username: str) -> None:
    _fail_records.pop(username.lower(), None)


# ------------------------------------------------------------------ 工具


def _public_user(row: dict) -> dict:
    """把数据库行转成可以安全发给前端的形状（**绝不含密码字段**）。"""
    return {
        "user_id": int(row["UserID"]),
        "username": row["Username"],
        "display_name": row.get("DisplayName") or row["Username"],
        "role": row.get("Role") or "student",
    }


def _issue(row: dict) -> dict:
    token = create_token(int(row["UserID"]), row["Username"], DEFAULT_TTL_SECONDS)
    return {
        "token": token,
        "token_type": "Bearer",
        "expires_in": DEFAULT_TTL_SECONDS,
        "user": _public_user(row),
    }


# --------------------------------------------------------------- 注册


@router.post("/register", summary="注册新账号")
def register(body: RegisterBody) -> dict:
    username = body.username.strip()

    if (msg := check_username(username)) is not None:
        raise HTTPException(status_code=400, detail=msg)
    if (msg := check_password_strength(body.password)) is not None:
        raise HTTPException(status_code=400, detail=msg)

    if users.find_by_username(username):
        raise HTTPException(status_code=409, detail="这个用户名已经被注册了，换一个吧")

    user_id = users.create_user(
        username=username,
        password_hash=hash_password(body.password),
        display_name=(body.display_name or "").strip() or username,
        role="student",
    )
    row = users.find_by_username(username)
    if not row:
        # 理论上不会发生；真发生了要说实话，不要假装成功
        raise HTTPException(status_code=500, detail=f"账号已写入（ID={user_id}）但读取失败，请重试")

    users.touch_last_login(int(row["UserID"]))
    result = _issue(dict(row))
    result["created"] = True
    return result


# --------------------------------------------------------------- 登录


@router.post("/login", summary="登录")
def login(body: LoginBody) -> dict:
    username = body.username.strip()

    wait = _is_locked(username)
    if wait > 0:
        raise HTTPException(
            status_code=429,
            detail=f"密码连续输错太多次，请等 {wait} 秒后再试",
        )

    row = users.find_by_username(username)

    # 注意：用户名不存在与密码错误，返回**完全相同**的提示
    if not row or not verify_password(body.password, row["PasswordHash"]):
        _record_fail(username)
        raise HTTPException(status_code=401, detail="用户名或密码不正确")

    if not row.get("IsActive"):
        raise HTTPException(status_code=403, detail="账号已被停用")

    _clear_fail(username)
    users.touch_last_login(int(row["UserID"]))
    return _issue(dict(row))


# ----------------------------------------------------------- 查看自己


@router.get("/me", summary="查看当前登录的账号")
def me(user: dict = Depends(current_user)) -> dict:
    return _public_user(user)


@router.get("/overview", summary="当前账号的数据概况（工作台首页用）")
def overview(user: dict = Depends(current_user)) -> dict:
    uid = user_id_of(user)
    return {
        "user": _public_user(user),
        "counts": {
            "datasets": data.count_datasets(uid),
            "charts": data.count_charts(uid),
            "dashboards": data.count_dashboards(uid),
        },
    }


@router.post("/logout", summary="退出登录")
def logout(user: dict = Depends(current_user)) -> dict:
    """令牌是无状态的，真正的"作废"由前端删掉本地令牌完成。

    这里保留一个接口，是为了让前端有个明确的动作可调用，
    也方便将来改造成"服务端吊销令牌"（比如加黑名单）。
    """
    return {"ok": True, "message": "已退出登录，请在前端删除本地令牌"}
