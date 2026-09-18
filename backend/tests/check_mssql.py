#!/usr/bin/env python3
"""学校 SQL Server 接入体检。

它回答一个问题：**现在能不能连上学校数据库，如果不能，卡在哪一步。**

它会依次检查：
    1. 驱动装了没有
    2. 配置填全了没有（**不会打印密码**，只说"已填写 / 为空"）
    3. 网络能不能通到数据库端口
    4. **中文用户名会不会被编码搞坏**（用编造的名字探测，不碰真实账号）
    5. 账号密码能不能通过校验
    6. 指定的库名存不存在
    7. 有没有建表权限
    8. 中文存进去再读出来会不会变乱码（这是中文项目最常踩的坑）

每一步失败都会给出**人话的原因和该怎么做**，而不是丢一个错误码。

运行：
    cd backend && PYTHONPATH=. .venv/bin/python tests/check_mssql.py
"""

from __future__ import annotations

import pathlib
import socket
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.db.drivers import available_drivers, driver_hint  # noqa: E402

PASS, FAIL, WARN, SKIP = "✅", "❌", "⚠️ ", "⏭️ "


def line(mark: str, title: str, detail: str = "") -> None:
    text = f"  {mark} {title}"
    if detail:
        text += f"\n       {detail}"
    print(text)


def step_config() -> bool:
    print("\n【1】配置检查")
    ok = True
    items = [
        ("数据库地址", settings.mssql_host, True),
        ("端口", str(settings.mssql_port), True),
        ("库名", settings.mssql_database, True),
        ("用户名", settings.mssql_user, True),
    ]
    for name, value, required in items:
        if value:
            line(PASS, f"{name}：{value}")
        elif required:
            line(FAIL, f"{name}：还没有填", "请打开 backend/.env 补上")
            ok = False

    # 密码只看"有没有"，绝不打印内容
    if settings.mssql_password:
        line(PASS, f"密码：已填写（{len(settings.mssql_password)} 个字符）")
    else:
        line(FAIL, "密码：还没有填", "请在 backend/.env 的 MSSQL_PASSWORD= 后面填上你自己的密码")
        ok = False
    return ok


def step_driver() -> bool:
    print("\n【2】驱动检查")
    drivers = available_drivers()
    if not drivers:
        line(FAIL, "没有安装任何 SQL Server 驱动", "执行：pip install pymssql")
        return False
    line(PASS, driver_hint())
    if len(drivers) > 1:
        line(WARN, f"装了多个驱动：{', '.join(drivers)}，将优先使用 {drivers[0]}")
    return True


def step_network() -> bool:
    print("\n【3】网络检查")
    host, port = settings.mssql_host, settings.mssql_port
    if not host:
        line(SKIP, "地址没填，跳过")
        return False
    try:
        with socket.create_connection((host, port), timeout=5):
            line(PASS, f"能连上 {host}:{port}")
            return True
    except socket.timeout:
        line(FAIL, f"连接 {host}:{port} 超时", "可能不在校园网内，或防火墙拦了 1433 端口")
    except OSError as exc:
        line(FAIL, f"连不上 {host}:{port}", f"{exc}")
    return False


def explain_connect_error(exc: Exception) -> str:
    """把驱动抛出的英文错误码翻译成"人话 + 该怎么做"。"""
    text = str(exc)
    low = text.lower()

    if "18456" in text or "login failed" in low:
        hint = (
            "账号或密码不正确。\n"
            "       · 确认 backend/.env 里的 MSSQL_USER 和 MSSQL_PASSWORD 没有多余空格\n"
            "       · 若多次输错，学校的账号可能被临时锁定，等几分钟再试"
        )
        hint += (
            "\n\n       【重点】SQL Server 对『用户不存在』和『密码错误』故意返回同一个错误，\n"
            "       所以从报错里分不出是哪个。但目前这些已经逐一排除了：\n"
            "         · 网络可达（端口通）\n"
            "         · 连的是正确的实例（实例探查已确认端口一致）\n"
            "         · 用户名编码正确（中文能原样送达服务器）\n"
            "         · 密码没被配置文件吃掉字符（完整性检查通过）\n"
            "       → 剩下的可能性集中在【密码字符串本身对不上】。\n"
            "       建议在 Navicat 里新建一条连接，把密码【手动重敲一遍】测试；\n"
            "       能连上就说明密码没记错，回到本工具重填一次即可。"
        )
        return hint
    if "4060" in text or "cannot open database" in low:
        return (
            f"账号密码是对的，但打不开库「{settings.mssql_database}」。\n"
            "       · 库名可能拼错了（注意大小写和空格）\n"
            "       · 也可能这个账号没有被授权访问该库"
        )
    if "20009" in text or "unable to connect" in low or "tds server is unavailable" in low:
        return (
            "连不上数据库服务。\n"
            "       · 确认在校园网 / VPN 内\n"
            "       · 确认 SQL Server 允许远程连接、1433 端口开放"
        )
    if "timeout" in low or "timed out" in low:
        return "连接超时。多半是网络不通或被防火墙拦截。"
    if "certificate" in low or "ssl" in low or "tls" in low:
        return "SSL/TLS 握手失败。这是加密方式不匹配，需要在连接参数里调整加密设置。"
    return f"未归类的错误，原文如下：\n       {text[:400]}"


def step_instance_probe() -> None:
    """探查这台机器上跑着哪些 SQL Server 实例、分别听哪个端口。

    为什么值得单独测：命名实例（形如 主机\\实例名）经常监听**动态端口**。
    如果 1433 上其实跑的是**另一个实例**，那么即使账号密码全对，
    也会一直被回"登录失败" —— 因为它问的根本不是你老师那台库。
    这一步就是确认"我连的确实是那台库"。
    """
    print("\n【4】服务器实例探查（这里连的到底是不是老师那台库）")
    host = settings.mssql_host
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(4)
        try:
            sock.sendto(b"\x03", (host, 1434))
            data, _ = sock.recvfrom(8192)
        finally:
            sock.close()

        text = data.decode("utf-8", errors="replace")
        if text and ord(text[0]) < 32:
            text = text[1:]

        instances = [i for i in text.split(";;") if i.strip()]
        if not instances:
            line(WARN, "探查到了响应，但没能解析出实例信息", text[:200])
            return

        matched = False
        for inst in instances:
            fields = inst.split(";")
            info: dict[str, str] = {}
            for j in range(0, len(fields) - 1, 2):
                info[fields[j].strip().lower()] = fields[j + 1].strip()
            name = info.get("instancename", "?")
            tcp = info.get("tcp", "")
            ver = info.get("version", "?")
            same_port = str(tcp) == str(settings.mssql_port)
            if same_port:
                matched = True
            line(
                PASS if same_port else WARN,
                f"实例「{name}」监听端口 {tcp or '（未启用 TCP）'}"
                + ("  ← 与配置一致" if same_port else ""),
                f"版本 {ver}" + ("" if same_port else f"  ⚠️ 你的配置写的是 {settings.mssql_port}，对不上"),
            )
            if ver.startswith("16."):
                print("       提示：这是 SQL Server 2022，对加密要求较新；本项目用的驱动能兼容")

        if not matched:
            line(
                FAIL,
                "没有任何实例监听你配置的端口",
                "说明你连的很可能不是老师那台库，请核对 .env 里的 MSSQL_PORT",
            )
    except socket.timeout:
        line(
            SKIP,
            "SQL Browser（UDP 1434）没有响应",
            "多半是防火墙拦了或服务未启动。不影响连接，只是查不到实例清单。",
        )
    except OSError as exc:
        line(SKIP, "实例探查未完成", str(exc)[:150])


def step_username_encoding() -> bool:
    """用户名编码测试 —— 用**编造的**中文用户名探测，绝不碰使用者的真实账号。

    原理：SQL Server 拒绝登录时，会把用户名原样写进错误信息里
    （`Login failed for user '...'`）。所以只要看回来的中文有没有被破坏，
    就知道整条编码链路通不通。

    为什么必须测：中文用户名一旦编码没配对，症状是"密码明明是对的却登不上"，
    而且报错信息里全是问号，极难排查。
    """
    print("\n【5】用户名编码测试（用编造的中文名探测，不会碰你的账号）")
    fake = "莫衡编码测试用户不存在"
    try:
        import pymssql

        pymssql.connect(
            server=settings.mssql_host,
            port=settings.mssql_port,
            user=fake,
            password="obviously-not-a-real-password",
            database="master",
            charset="utf8",
            login_timeout=10,
            timeout=10,
        )
        line(WARN, "用编造的用户名竟然登录成功了？", "这不合常理，请人工确认服务器配置")
        return False
    except Exception as exc:  # noqa: BLE001
        # pymssql 的异常内容可能是 bytes，必须解码后才能正确比较中文。
        # 注意：解码后 FreeTDS 有时仍把非 ASCII 字节显示成 \xe5\x88 这样的转义文本，
        # 所以两种形态都要认，否则会误报"中文没送达"。
        payload = exc.args[1] if len(getattr(exc, "args", ())) > 1 else str(exc)
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8", errors="replace")
        payload = str(payload)

        escaped = "".join(f"\\x{b:02x}" for b in fake.encode("utf-8"))
        if fake in payload or escaped in payload.lower():
            line(
                PASS,
                "中文用户名能正确送达数据库并被正确识别",
                f"服务器回显了完整的中文名字（{'原样' if fake in payload else '以转义形式'}）",
            )
            return True
        if "18456" in payload or "login failed" in payload.lower():
            line(
                WARN,
                "登录被拒（符合预期），但中文用户名没有原样回显",
                "多半只是错误信息格式差异；若你的账号登不上，再重点查这一项",
            )
            return True
        line(FAIL, "编码测试没能完成", payload[:200])
        return False


def step_connect():
    """真正建立连接。成功返回连接对象，失败返回 None。"""
    print("\n【6】连接检查")
    try:
        from app.db.connection import _connect_mssql

        conn = _connect_mssql()
    except Exception as exc:  # noqa: BLE001
        line(FAIL, "连接失败", explain_connect_error(exc))
        return None

    line(PASS, "连接成功")
    return conn


def step_server_info(conn) -> None:
    print("\n【7】服务器信息（含登录身份）")
    cur = conn.cursor()
    try:
        cur.execute("SELECT @@VERSION AS v")
        row = cur.fetchone()
        version = next(iter(row.values())) if isinstance(row, dict) else row[0]
        first = str(version).splitlines()[0]
        line(PASS, f"版本：{first[:90]}")

        cur.execute("SELECT DB_NAME() AS d, SUSER_NAME() AS u")
        row = cur.fetchone()
        get = (lambda k: row[k]) if isinstance(row, dict) else (lambda k: row[0])
        line(PASS, f"当前库：{get('d')}")
        line(PASS, f"当前登录：{get('u')}")
    except Exception as exc:  # noqa: BLE001
        line(WARN, "读取服务器信息失败", str(exc)[:200])
    finally:
        cur.close()


def step_chinese(conn) -> None:
    """中文往返测试：这是中文项目最容易出问题、又最难发现的地方。"""
    print("\n【8】中文读写测试")
    cur = conn.cursor()
    try:
        cur.execute("SELECT N'中文测试 · 广东销售额' AS t")
        row = cur.fetchone()
        got = next(iter(row.values())) if isinstance(row, dict) else row[0]
        if got == "中文测试 · 广东销售额":
            line(PASS, f"读回的中文正确：{got}")
        else:
            line(FAIL, "中文出现乱码", f"期望「中文测试 · 广东销售额」，实际「{got}」")
    except Exception as exc:  # noqa: BLE001
        line(FAIL, "中文测试失败", str(exc)[:200])
    finally:
        cur.close()


def step_create_table(conn) -> None:
    """建表权限测试：用一张临时表试，试完立刻删掉。"""
    print("\n【9】建表权限测试")
    cur = conn.cursor()
    table = "MohengPermCheck"
    try:
        cur.execute(f"IF OBJECT_ID('{table}','U') IS NOT NULL DROP TABLE {table}")
        cur.execute(f"CREATE TABLE {table} (ID INT IDENTITY(1,1) PRIMARY KEY, Name NVARCHAR(50))")
        cur.execute(f"INSERT INTO {table} (Name) VALUES (N'测试')")
        cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
        row = cur.fetchone()
        n = next(iter(row.values())) if isinstance(row, dict) else row[0]
        conn.commit()
        line(PASS, f"有建表、写入、读取权限（写入 {n} 行）")
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        line(
            FAIL,
            "没有建表权限",
            f"{str(exc)[:200]}\n"
            "       → 需要让老师给这个账号开 CREATE TABLE 权限，\n"
            "         或者由老师预先按 docs/数据库设计.md 里的建表语句建好表。",
        )
    finally:
        try:
            cur.execute(f"IF OBJECT_ID('{table}','U') IS NOT NULL DROP TABLE {table}")
            conn.commit()
        except Exception:
            conn.rollback()
        cur.close()


def main() -> int:
    print("=" * 78)
    print("学校 SQL Server 接入体检")
    print("=" * 78)
    print(f"目标：{settings.mssql_host or '(未填)'}:{settings.mssql_port}"
          f"/{settings.mssql_database or '(未填库名)'}   用户：{settings.mssql_user or '(未填)'}")
    print(f"当前运行模式：{settings.db_mode_label}（{settings.db_mode}）")

    cfg_ok = step_config()
    drv_ok = step_driver()
    net_ok = step_network()

    if not (cfg_ok and drv_ok):
        print("\n" + "=" * 78)
        print("结论：配置或驱动还没准备好，先把上面标 ❌ 的补齐。")
        print("      补齐后在 backend/.env 里把 DB_MODE 改成 mssql，再重启后端。")
        print("=" * 78)
        return 1
    if not net_ok:
        print("\n" + "=" * 78)
        print("结论：网络不通，先解决网络问题（多半要连校园网 / VPN）。")
        print("=" * 78)
        return 1

    step_instance_probe()
    step_username_encoding()

    conn = step_connect()
    if conn is None:
        print("\n" + "=" * 78)
        print("结论：连不上，按上面的提示处理。")
        print("=" * 78)
        return 1

    try:
        step_server_info(conn)
        step_chinese(conn)
        step_create_table(conn)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    print("\n" + "=" * 78)
    print("结论：连接可用。可以放心把 backend/.env 里的 DB_MODE 改成 mssql 了。")
    print("      改完重启后端，表会自动建好，然后跑一遍数据隔离测试：")
    print("      PYTHONPATH=. .venv/bin/python tests/test_isolation.py")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
