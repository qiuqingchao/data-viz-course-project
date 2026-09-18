#!/usr/bin/env python3
"""账号接口的端到端测试（对着**真实运行中的后端**发 HTTP 请求）。

和 tests/test_isolation.py 的区别：
    那个测的是"数据访问层"（函数级）；
    这个测的是"接口层"（真发 HTTP 请求），包括密码错误、令牌篡改、
    暴力破解锁定这些只有在真实请求里才暴露的问题。

前置条件：后端已在 127.0.0.1:8000 运行。

运行：
    cd backend && .venv/bin/python tests/test_auth_http.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")

# 读 .env 里真正的演示密码（不写死在任何地方）
ENV_FILE = pathlib.Path(__file__).resolve().parent.parent / ".env"


def read_env(key: str) -> str:
    if not ENV_FILE.exists():
        return ""
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


_results: list[tuple[bool, str, str]] = []


def check(ok: bool, title: str, detail: str = "") -> bool:
    _results.append((bool(ok), title, detail))
    return bool(ok)


def call(
    method: str,
    path: str,
    body: dict | None = None,
    token: str | None = None,
) -> tuple[int, dict]:
    """发一个请求，返回 (状态码, 响应内容)。网络错误返回 (0, {...})。"""
    url = f"{BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw}
    except Exception as e:
        return 0, {"error": f"{type(e).__name__}: {e}"}


def main() -> int:
    print("账号接口端到端测试（真实 HTTP）")
    print("=" * 78)
    print(f"目标：{BASE}")

    # ---------------------------------------------------- 后端是否活着
    status, health = call("GET", "/api/health")
    if not check(status == 200, "后端可访问", f"状态码={status}"):
        print("后端没起来，测试无法继续。")
        return 1
    print(f"数据库：{health['database']['mode_label']} — {health['database']['message']}")
    print()

    demo_user = read_env("DEMO_USERNAME") or "demo"
    demo_pw = read_env("DEMO_PASSWORD")

    # ------------------------------------------- 登录失败的各种情形
    print("─" * 78)
    print("一、登录/注册的失败路径（能不能挡住不该进来的）")
    print("─" * 78)

    status, body = call("POST", "/api/auth/login", {"username": "no_such_user_xyz", "password": "whatever"})
    check(status == 401, "不存在的用户名 → 401 拒绝", f"状态码={status}")

    status, body = call("POST", "/api/auth/login", {"username": demo_user, "password": "definitely-wrong"})
    check(status == 401, "密码错误 → 401 拒绝", f"状态码={status}")
    wrong_msg = body.get("detail", "")

    status, body2 = call("POST", "/api/auth/login", {"username": "no_such_user_xyz", "password": "whatever"})
    same_msg = body2.get("detail", "")
    check(
        wrong_msg == same_msg and wrong_msg == "用户名或密码不正确",
        "用户名不存在与密码错误 → 提示完全相同（不泄露用户名是否存在）",
        f"「{wrong_msg}」vs「{same_msg}」",
    )

    status, body = call("POST", "/api/auth/register", {"username": "ab", "password": "GoodPass123"})
    check(status == 400, "用户名过短 → 400 拒绝", f"状态码={status}，{body.get('detail')}")

    status, body = call("POST", "/api/auth/register", {"username": "bad name!", "password": "GoodPass123"})
    check(status == 400, "用户名含非法字符 → 400 拒绝", f"状态码={status}，{body.get('detail')}")

    status, body = call("POST", "/api/auth/register", {"username": "valid_user_x", "password": "123"})
    check(status == 400, "密码过短 → 400 拒绝", f"状态码={status}，{body.get('detail')}")

    status, body = call("POST", "/api/auth/register", {"username": "valid_user_x", "password": "12345678"})
    check(status == 400, "纯数字密码 → 400 拒绝", f"状态码={status}，{body.get('detail')}")

    # ---------------------------------------------------- 注册成功
    print()
    print("─" * 78)
    print("二、注册与登录的正常路径")
    print("─" * 78)

    # 用一个不会撞车的用户名（带上时间戳的尾巴）
    import time

    uname = f"stu_{int(time.time()) % 100000}"
    new_pw = "CourseDesign2026"
    status, body = call("POST", "/api/auth/register", {"username": uname, "password": new_pw, "display_name": "测试同学"})
    ok = check(status == 200 and body.get("token"), "注册新账号 → 成功并直接签发令牌", f"状态码={status}，{body.get('detail', '')}")
    token_new = body.get("token", "") if ok else ""

    if ok:
        check(
            "password" not in json.dumps(body).lower() and "scrypt" not in json.dumps(body).lower(),
            "注册响应里**不含任何密码信息**（明文和哈希都不该出现）",
            f"响应字段={list(body.keys())}",
        )
        check(body["user"]["username"] == uname, "返回的用户名正确")
        check(body["user"]["display_name"] == "测试同学", "返回的显示名正确")
        check("user_id" in body["user"] and body["user"]["user_id"] > 0, "返回了用户 ID")

    status, body = call("POST", "/api/auth/register", {"username": uname, "password": new_pw})
    check(status == 409, "重复注册同一个用户名 → 409 拒绝", f"状态码={status}，{body.get('detail')}")

    if demo_pw:
        status, body = call("POST", "/api/auth/login", {"username": demo_user, "password": demo_pw})
        check(status == 200 and body.get("token"), "演示账号用正确密码登录 → 成功", f"状态码={status}")
        demo_token = body.get("token", "") if status == 200 else ""
    else:
        check(False, "演示账号登录", ".env 里没有 DEMO_PASSWORD")
        demo_token = ""

    # ---------------------------------------------------- 令牌校验
    print()
    print("─" * 78)
    print("三、令牌（进门手环）能不能挡住伪造")
    print("─" * 78)

    status, body = call("GET", "/api/auth/me")
    check(status == 401, "不带令牌访问 /me → 401", f"状态码={status}")

    status, body = call("GET", "/api/auth/me", token="garbage-token")
    check(status == 401, "乱码令牌 → 401", f"状态码={status}")

    if token_new:
        status, body = call("GET", "/api/auth/me", token=token_new)
        check(status == 200 and body.get("username") == uname, "带正确令牌访问 /me → 拿到自己的身份", f"状态码={status}")

        # 篡改签名
        forged = token_new[:-6] + "AAAAAA"
        status, body = call("GET", "/api/auth/me", token=forged)
        check(status == 401, "篡改签名的令牌 → 401（无法伪造成别人）", f"状态码={status}")

        # 篡改内容但保留旧签名
        head, _, sig = token_new.partition(".")
        status, body = call("GET", "/api/auth/me", token=f"{head[:-4]}AAAA.{sig}")
        check(status == 401, "篡改内容的令牌 → 401", f"状态码={status}")

    status, body = call("GET", "/api/auth/overview", token=demo_token)
    check(
        status == 200 and "counts" in body,
        "带令牌查询数据概况 → 成功",
        f"状态码={status}",
    )
    if status == 200:
        counts = body["counts"]
        check(
            all(k in counts for k in ("datasets", "charts", "dashboards")),
            "概况里包含数据集/图表/大屏三类计数",
            f"{counts}",
        )

    # ------------------------------------------------ 暴力破解防护
    print()
    print("─" * 78)
    print("四、暴力破解防护（连续猜密码会被暂时锁住）")
    print("─" * 78)

    victim = f"locktarget_{int(time.time()) % 100000}"
    call("POST", "/api/auth/register", {"username": victim, "password": "CorrectHorse99"})

    codes = []
    for _ in range(7):
        status, _b = call("POST", "/api/auth/login", {"username": victim, "password": "guess"})
        codes.append(status)

    check(
        429 in codes,
        "连续输错 5 次后 → 429 暂时锁定",
        f"7 次尝试的状态码={codes}",
    )
    check(
        codes[:5] == [401] * 5,
        "锁定之前都是正常的 401（前 5 次不锁，避免误伤打错一次的人）",
        f"前 5 次={codes[:5]}",
    )

    # 锁定期间，即使密码对了也应该被挡住
    status, body = call("POST", "/api/auth/login", {"username": victim, "password": "CorrectHorse99"})
    check(status == 429, "锁定期间即使密码正确也拒绝（锁定真的生效）", f"状态码={status}")

    # ------------------------------------------------------- 善后清理
    # 这个测试会往**开发库**里建几个账号。用完必须自己打扫干净，
    # 否则跑几次之后数据库里就堆一堆 stu_xxx、locktarget_xxx 的垃圾账号。
    cleanup_errors: list[str] = []
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
        from app.db.connection import execute

        for name in (uname, victim):
            try:
                execute("DELETE FROM Users WHERE Username = ?", [name])
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(f"{name}: {exc}")
    except Exception as exc:  # noqa: BLE001
        cleanup_errors.append(f"无法连接数据库：{exc}")

    check(
        not cleanup_errors,
        "善后：测试创建的临时账号已清理（不污染开发库）",
        "；".join(cleanup_errors),
    )

    # ------------------------------------------------------- 汇总
    print()
    print("=" * 78)
    passed = sum(1 for ok, _, _ in _results if ok)
    total = len(_results)
    for ok, title, detail in _results:
        mark = "✅" if ok else "❌"
        line = f"  {mark} {title}"
        if detail and not ok:
            line += f"\n        → {detail}"
        print(line)
    print("=" * 78)
    print(f"结果：{passed}/{total} 通过")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
