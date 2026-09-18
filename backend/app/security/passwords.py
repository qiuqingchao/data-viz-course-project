"""密码加密。

**只存加密后的乱码，永不存明文。** 这是本模块存在的全部意义。

用的算法：**scrypt**（Python 标准库自带，不需要额外装任何零件）。

为什么选它？
    密码加密有两条路：
      · 快速哈希（MD5/SHA256）—— **绝对不能用**。它算得太快，
        显卡每秒能试几十亿次，弱密码几分钟就被撞出来。
      · 慢哈希（scrypt / bcrypt / Argon2）—— 故意算得慢，还吃内存。
        scrypt 除了慢，还要求大量内存，这让"用显卡暴力破解"变得极其昂贵。

    scrypt 已被 OWASP（国际权威安全组织）列为推荐的密码哈希算法之一，
    而且 Python 自带 —— 少装一个库就少一分风险和维护成本。

存储格式（自带算法参数，方便将来升级）：
    scrypt$n=16384,r=8,p=1$<盐的base64>$<哈希的base64>

    把参数写在里面，是为了将来某天想提高强度时，老密码依然能验证通过。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

# ---- 算法参数。数字越大越安全，但登录越慢（这四个值约需 50~100 毫秒，体感无感）----
_N = 16384  # CPU/内存代价
_R = 8  # 块大小
_P = 1  # 并行度
_DKLEN = 32  # 输出长度（字节）
_SALT_BYTES = 16
_MAXMEM = 64 * 1024 * 1024  # 允许 scrypt 使用的最大内存

MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 128


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def hash_password(password: str) -> str:
    """把明文密码变成可安全入库的乱码。"""
    if not password:
        raise ValueError("密码不能为空")
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN, maxmem=_MAXMEM
    )
    return f"scrypt$n={_N},r={_R},p={_P}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str | None) -> bool:
    """校验密码。任何时候都不抛异常，只回 True/False。"""
    if not password or not stored:
        return False
    try:
        algo, params, salt_b64, hash_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        kv = dict(item.split("=") for item in params.split(","))
        n, r, p = int(kv["n"]), int(kv["r"]), int(kv["p"])
        salt = _unb64(salt_b64)
        expected = _unb64(hash_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(expected), maxmem=_MAXMEM
        )
        # 必须用"恒定时间比较"，否则可以通过测量耗时一个字符一个字符地猜出密码
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def check_password_strength(password: str) -> str | None:
    """给用户看的密码强度提示。返回 None 表示合格，否则返回人话原因。"""
    if not password:
        return "密码不能为空"
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"密码至少 {MIN_PASSWORD_LENGTH} 位"
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"密码不能超过 {MAX_PASSWORD_LENGTH} 位"
    if password.isdigit():
        return "密码不能全是数字"
    if password.lower() in {"123456", "password", "admin", "111111", "abc123"}:
        return "这个密码太常见了，换一个"
    return None


def check_username(username: str) -> str | None:
    """用户名合法性。返回 None 表示合格。"""
    if not username:
        return "用户名不能为空"
    if len(username) < 3 or len(username) > 32:
        return "用户名长度需在 3~32 位之间"
    if not all(ch.isalnum() or ch == "_" or ch == "-" for ch in username):
        return "用户名只能包含字母、数字、下划线和中划线"
    return None
