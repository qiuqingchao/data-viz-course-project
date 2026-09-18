"""接口的公共依赖：把"当前登录的是谁"这件事变成一行代码。

用法：
    @router.get("/xxx")
    def some_api(user: dict = Depends(current_user)):
        ...  # 这里的 user["UserID"] 就是要传给数据层的 user_id

这样每个需要登录的接口，都**不可能忘记**校验身份 ——
忘了写 Depends，接口就等于没有身份，一测就露馅。
"""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from ..db import users
from ..security.tokens import read_token


def _unauthorized(reason: str = "登录状态已失效，请重新登录") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=reason,
        headers={"WWW-Authenticate": "Bearer"},
    )


def current_user(authorization: str | None = Header(default=None)) -> dict:
    """从请求头里取出令牌，验证并返回当前用户。

    浏览器发来的格式是：Authorization: Bearer <令牌>
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("缺少登录令牌")

    token = authorization.split(" ", 1)[1].strip()
    payload = read_token(token)
    if not payload:
        raise _unauthorized("令牌无效或已过期")

    user = users.find_by_id(int(payload["sub"]))
    if not user:
        raise _unauthorized("账号不存在")
    if not user.get("IsActive"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被停用")
    return user


def user_id_of(user: dict) -> int:
    """统一从用户字典里取 ID，避免各处写 user["UserID"] 写错大小写。"""
    return int(user["UserID"])
