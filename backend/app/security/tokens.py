"""登录令牌（相当于"进门后发的手环"）。

为什么需要它？
    网页是无状态的：登录成功后，后续每个请求都得证明"我是谁"。
    做法是登录成功时发一个**签过名的令牌**给浏览器，浏览器每次请求都带上它。

为什么不用网上常见的 JWT 库？
    一个 JWT 无非就是"把内容 + 签名拼成一串"，核心只有 HMAC-SHA256 一行。
    Python 标准库自带 hmac 和 hashlib，自己按规范写 40 行就够，
    而且逻辑完全可见、可审计 —— 比多装一个库更符合本项目的"轻量、可控"。
    安全要点一个都不能省（见下），省一个就会变成漏洞。

必须守住的三条：
    1. **签名**：内容被篡改，签名立刻对不上 → 拒绝。别人改不了自己的 UserID。
    2. **恒定时间比较**：防止通过测量比较耗时来一点点猜出签名。
    3. **过期时间**：令牌不会永久有效，泄露了也有时间窗口。

诚实边界：
    这是"够课设用、写法正确"的方案。真要上生产，还应该加上
    HTTPS、令牌吊销（黑名单）、刷新令牌等机制 —— 那些不在课设范围内。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import warnings

from ..config import settings

DEFAULT_TTL_SECONDS = 7 * 24 * 3600  # 7 天


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64url(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _secret() -> bytes:
    """取签名密钥。

    密钥必须放在 .env 里（不进代码、不进版本库）。
    万一没配，就临时生成一个并**大声警告** ——
    这样开发时不会卡住，但也不会让人误以为"没配也没关系"。
    """
    key = settings.secret_key
    if not key:
        warnings.warn(
            "SECRET_KEY 未配置，已临时生成一个。重启后端后所有登录会失效。"
            "请在 backend/.env 里设置 SECRET_KEY。",
            RuntimeWarning,
            stacklevel=2,
        )
        key = secrets.token_urlsafe(48)
        settings.secret_key = key  # 本次进程内复用同一个
    return key.encode("utf-8")


def create_token(user_id: int, username: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """签发令牌。"""
    now = int(time.time())
    payload = {
        "sub": int(user_id),
        "u": username,
        "iat": now,
        "exp": now + int(ttl_seconds),
        # 随机串：保证同一用户每次登录拿到不同令牌，避免重放
        "jti": secrets.token_urlsafe(8),
    }
    body = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    sig = _b64url(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(token: str | None) -> dict | None:
    """验证令牌。合法返回内容，任何问题一律返回 None。"""
    if not token or token.count(".") != 1:
        return None
    body, sig = token.split(".", 1)
    try:
        expected = _b64url(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
        # 恒定时间比较，防"时序攻击"
        if not hmac.compare_digest(expected, sig):
            return None
        payload = json.loads(_unb64url(body).decode("utf-8"))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None  # 已过期
    if not payload.get("sub"):
        return None
    return payload


def new_share_token() -> str:
    """生成只读分享链接用的随机串（第 6 阶段用）。

    长度足够、完全随机，猜不出来 —— 这是分享链接唯一的"钥匙"。
    """
    return secrets.token_urlsafe(24)
