#!/usr/bin/env python3
"""数据隔离测试 —— 本项目最核心的一条防线，必须由测试来证明。

要证明的事情只有一件：
    **甲用户绝对看不到、改不了、删不掉乙用户的数据。**

测试分两层：
    第一层（动态）真实建两个用户、各造数据，然后让甲去"偷"乙的数据，
                  逐个验证：查不到、改不动、删不掉。
    第二层（静态）扫描数据访问层里每一个函数，确认它们**都**带了 user_id，
                  防止将来有人加新函数时忘了隔离。

运行：
    cd backend && PYTHONPATH=. .venv/bin/python tests/test_isolation.py

    想在真实学校数据库上跑（这才是真正的验证）：
    cd backend && ISOLATION_TARGET=mssql PYTHONPATH=. .venv/bin/python tests/test_isolation.py

为什么默认用临时数据库？
    不能在开发库上跑测试 —— 测试会建用户、造数据、删数据。
    所以默认把数据库指向一个临时文件，跑完就丢。

在真实数据库上跑时会发生什么？
    · 会**在你的库里**建两个测试账号、造几条测试数据
    · 跑完会**自动全部删掉**（并用 atexit 兜底：即使中途崩溃也会清理）
    · 测试账号名固定为 alice_test / bob_test，开工前会先清理同名残留
    · 只有真实数据库才能验证"中文表名/排序规则/事务行为"这些 SQLite 测不出的东西
"""

from __future__ import annotations

import atexit
import os
import pathlib
import sys
import tempfile

# ---------------------------------------------------------------- 环境准备
# 必须在 import app.* 之前设置：配置模块只在"环境变量不存在"时才读 .env
#
# 默认跑在临时 SQLite 上（安全、快、不污染任何库）。
# 传 ISOLATION_TARGET=mssql 则改为在 .env 配置的真实数据库上跑 ——
# 这时**不要**覆盖 DB_MODE 和 SQLITE_PATH，让 .env 说了算。
TARGET = os.environ.get("ISOLATION_TARGET", "sqlite").strip().lower()
IS_REAL_DB = TARGET == "mssql"

_TMP_DIR = ""
if not IS_REAL_DB:
    _TMP_DIR = tempfile.mkdtemp(prefix="moheng-isolation-")
    os.environ["SQLITE_PATH"] = str(pathlib.Path(_TMP_DIR) / "isolation-test.db")
    os.environ["DB_MODE"] = "sqlite"

os.environ["SECRET_KEY"] = "isolation-test-secret-do-not-use-anywhere-else"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.db import bootstrap, data, users  # noqa: E402
from app.security.passwords import hash_password, verify_password  # noqa: E402
from app.security.tokens import create_token, read_token  # noqa: E402

# 固定的测试账号名：便于反复运行时识别和清理残留
TEST_USERNAMES = ("alice_test", "bob_test")

# ---------------------------------------------------------------- 善后清理
# 在真实数据库上跑测试，必须保证不留垃圾。
# 这里用 atexit 注册，好处是**即使测试中途抛异常/崩溃**，清理也会执行。
# 之前有过教训：依赖"临时文件跑完即弃"的测试，一旦搬到真实数据库上，
# 就会在别人的库里留下一堆测试数据。
_created_uids: list[int] = []


def _purge_user(uid: int) -> None:
    """删掉一个用户的全部数据，最后删账号本身（先子表后主表，避免外键报错）。"""
    from app.db.connection import execute

    execute("DELETE FROM Dashboards WHERE UserID = ?", [uid])
    execute("DELETE FROM Charts WHERE UserID = ?", [uid])
    execute("DELETE FROM Datasets WHERE UserID = ?", [uid])
    execute("DELETE FROM Users WHERE UserID = ?", [uid])


def _purge_by_username(username: str) -> None:
    from app.db.connection import query_one

    row = query_one("SELECT UserID FROM Users WHERE Username = ?", [username])
    if row:
        _purge_user(int(next(iter(row.values()))))


def cleanup(verbose: bool = False) -> None:
    """清理本次测试产生的所有数据。可以被重复调用（幂等）。"""
    for uid in list(_created_uids):
        try:
            _purge_user(uid)
            if verbose:
                print(f"    已清理测试用户 ID={uid}")
        except Exception as exc:  # noqa: BLE001
            print(f"    ⚠️ 清理用户 {uid} 失败：{type(exc).__name__}: {str(exc)[:80]}")
    _created_uids.clear()
    # 再按名字扫一遍，兜住"上次跑崩了留下同名账号"的情况
    for name in TEST_USERNAMES:
        try:
            _purge_by_username(name)
        except Exception as exc:  # noqa: BLE001
            print(f"    ⚠️ 按名字清理 {name} 失败：{type(exc).__name__}: {str(exc)[:80]}")


atexit.register(cleanup)  # 兜底：中途崩溃也会清理

# ---------------------------------------------------------------- 测试脚手架
_results: list[tuple[bool, str, str]] = []


def check(ok: bool, title: str, detail: str = "") -> bool:
    _results.append((bool(ok), title, detail))
    return bool(ok)


def main() -> int:
    print("数据隔离测试")
    print("=" * 78)
    print(f"测试库（临时，跑完即弃）：{os.environ['SQLITE_PATH']}")
    print()

    # ---------------------------------------------------------- 准备阶段
    from app.config import settings

    bootstrap.bootstrap(verbose=False)

    if IS_REAL_DB:
        print(f"⚠️  目标：真实数据库 {settings.db_mode_label}")
        print(f"   {settings.mssql_host}:{settings.mssql_port}/{settings.mssql_database}")
        print("   会在库里建两个测试账号，跑完自动删除（含崩溃兜底）。")
    else:
        print(f"目标：临时 SQLite（跑完即弃）：{_TMP_DIR}")

    # 先清掉可能残留的同名测试账号（上次跑崩留下的）
    cleanup()
    print()

    pw_a, pw_b = "AlicePass123", "BobPass456"
    uid_a = users.create_user("alice_test", hash_password(pw_a), "甲同学")
    uid_b = users.create_user("bob_test", hash_password(pw_b), "乙同学")
    _created_uids.extend([uid_a, uid_b])  # 登记，供善后清理

    check(uid_a != uid_b and uid_a > 0 and uid_b > 0, "两个测试用户创建成功", f"甲={uid_a} 乙={uid_b}")

    # 各造一份数据：数据集、图表、大屏
    ds_a = data.create_dataset(
        uid_a, "甲的数据集", [{"name": "省份", "type": "text"}], [{"省份": "广东", "销售额": 100}]
    )
    ds_b = data.create_dataset(
        uid_b, "乙的机密数据集", [{"name": "省份", "type": "text"}], [{"省份": "江苏", "销售额": 999}]
    )
    chart_a = data.create_chart(uid_a, "甲的图表", "bar", {"x": 1}, ds_a)
    chart_b = data.create_chart(uid_b, "乙的机密图表", "pie", {"x": 2}, ds_b)
    dash_a = data.create_dashboard(uid_a, "甲的大屏", {"panels": []})
    dash_b = data.create_dashboard(uid_b, "乙的机密大屏", {"panels": []})

    print("─" * 78)
    print("第一层：动态隔离（甲去偷乙的数据）")
    print("─" * 78)

    # ---------------------------------------------------------- 数据集
    a_list = data.list_datasets(uid_a)
    ids_a = {r["DatasetID"] for r in a_list}
    check(
        ds_b not in ids_a and len(a_list) == 1,
        "【数据集】甲的列表里没有乙的数据集",
        f"甲看到 {len(a_list)} 条：{[r['Name'] for r in a_list]}",
    )

    got = data.get_dataset(uid_a, ds_b)
    check(got is None, "【数据集】甲按 ID 直接读取乙的数据集 → 返回空", f"实际={got!r}")

    # 尝试改乙的数据（这是最危险的操作：改别人的数据）
    affected = data.update_dataset(uid_a, ds_b, name="被甲改掉了")
    after = data.get_dataset(uid_b, ds_b)
    check(
        affected == 0 and after["Name"] == "乙的机密数据集",
        "【数据集】甲修改乙的数据集 → 影响 0 行，乙的数据原封不动",
        f"影响行数={affected}，乙的数据名={after['Name']!r}",
    )

    # 尝试删乙的数据
    deleted = data.delete_dataset(uid_a, ds_b)
    still = data.get_dataset(uid_b, ds_b)
    check(
        deleted == 0 and still is not None,
        "【数据集】甲删除乙的数据集 → 影响 0 行，乙的数据还在",
        f"删除行数={deleted}，乙的数据是否还在={still is not None}",
    )

    # 反向确认：甲对自己的数据是完全能操作的（别把功能锁死了）
    ok_self = data.update_dataset(uid_a, ds_a, name="甲自己改的名字") == 1
    check(ok_self, "【数据集】甲操作自己的数据集 → 正常生效（隔离没有误伤功能）")

    # 专门盯一类最隐蔽的 bug：受影响的**行数**必须精确。
    #
    # 真实踩过的坑：`execute()` 对 UPDATE 也去执行了一条取自增 ID 的查询，
    # 那条查询把游标的 rowcount 覆盖成 -1，于是"影响了几行"永远返回 -1。
    # 危害在于 -1 既不等于 0 也不等于 1：
    #   · 调用方写 if affected == 0 判断"这不是你的数据" → 永远不成立，隔离形同虚设
    #   · 写 if affected == 1 判断"更新成功" → 永远失败
    # 而数据其实一动没动，所以光看数据是查不出来的，必须直接断言行数。
    affected_one = data.update_dataset(uid_a, ds_a, name="甲再次改名")
    check(
        affected_one == 1,
        "【行数】更新命中 1 行时返回精确的 1（不能是 -1）",
        f"实际={affected_one}",
    )
    affected_zero = data.update_dataset(uid_a, 99999999, name="根本不存在的数据集")
    check(
        affected_zero == 0,
        "【行数】更新命中 0 行时返回精确的 0（调用方靠它判断'不是你的数据'）",
        f"实际={affected_zero}",
    )
    deleted_zero = data.delete_dataset(uid_a, 99999999)
    check(
        deleted_zero == 0,
        "【行数】删除命中 0 行时返回精确的 0",
        f"实际={deleted_zero}",
    )

    # ---------------------------------------------------------- 图表
    check(
        chart_b not in {r["ChartID"] for r in data.list_charts(uid_a)},
        "【图表】甲的列表里没有乙的图表",
    )
    check(data.get_chart(uid_a, chart_b) is None, "【图表】甲读取乙的图表 → 返回空")
    check(
        data.update_chart(uid_a, chart_b, title="被甲改了") == 0
        and data.get_chart(uid_b, chart_b)["Title"] == "乙的机密图表",
        "【图表】甲修改乙的图表 → 影响 0 行，乙的图表标题未变",
    )
    check(
        data.delete_chart(uid_a, chart_b) == 0 and data.get_chart(uid_b, chart_b) is not None,
        "【图表】甲删除乙的图表 → 影响 0 行，乙的图表还在",
    )

    # ---------------------------------------------------------- 大屏
    check(
        dash_b not in {r["DashboardID"] for r in data.list_dashboards(uid_a)},
        "【大屏】甲的列表里没有乙的大屏",
    )
    check(data.get_dashboard(uid_a, dash_b) is None, "【大屏】甲读取乙的大屏 → 返回空")
    check(
        data.update_dashboard(uid_a, dash_b, title="被甲改了") == 0
        and data.get_dashboard(uid_b, dash_b)["Title"] == "乙的机密大屏",
        "【大屏】甲修改乙的大屏 → 影响 0 行，乙的大屏标题未变",
    )
    check(
        data.delete_dashboard(uid_a, dash_b) == 0 and data.get_dashboard(uid_b, dash_b) is not None,
        "【大屏】甲删除乙的大屏 → 影响 0 行，乙的大屏还在",
    )

    # ------------------------------------------------- 只读分享链接的边界
    token = "share-token-for-testing-1234567890"
    data.set_share_token(uid_b, dash_b, token)
    check(
        data.get_shared_dashboard(token) is not None,
        "【分享】开启分享后，凭链接可以读到（这是设计允许的）",
    )
    check(
        data.get_shared_dashboard("wrong-token-0000000000000000") is None,
        "【分享】胡乱编一个链接 → 读不到",
    )
    check(
        data.get_shared_dashboard("short") is None,
        "【分享】过短的链接 → 直接拒绝（防止被猜）",
    )
    data.set_share_token(uid_b, dash_b, None)
    check(
        data.get_shared_dashboard(token) is None,
        "【分享】关闭分享后，原来的链接立即失效",
    )

    # ------------------------------------------------------- 账户安全
    print()
    print("─" * 78)
    print("第二层：账户安全（密码与令牌）")
    print("─" * 78)

    row = users.find_by_username("alice_test")
    check(pw_a not in row["PasswordHash"], "库里存的密码不是明文")
    check(verify_password(pw_a, row["PasswordHash"]), "正确密码能通过校验")
    check(not verify_password("WrongPass999", row["PasswordHash"]), "错误密码被拒绝")

    tok = create_token(uid_a, "alice_test", ttl_seconds=3600)
    payload = read_token(tok)
    check(payload is not None and int(payload["sub"]) == uid_a, "签发并读回令牌，身份一致")

    # 篡改令牌：把签名改掉
    body, _sig = tok.split(".", 1)
    check(read_token(f"{body}.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA") is None, "篡改签名 → 令牌失效")

    # 篡改内容：改掉用户 ID，但签名还是老的
    check(read_token(tok.replace(body, body[:-4] + "AAAA", 1)) is None, "篡改内容 → 令牌失效")

    expired = create_token(uid_a, "alice_test", ttl_seconds=-10)
    check(read_token(expired) is None, "过期令牌 → 失效")

    check(read_token("") is None and read_token(None) is None, "空令牌 → 失效")
    check(read_token("garbage") is None, "乱码令牌 → 失效")

    # ------------------------------------------------------- 静态检查
    print()
    print("─" * 78)
    print("第三层：静态检查（防止将来新加的函数漏掉隔离）")
    print("─" * 78)

    import inspect

    # 刻意不带 user_id 的豁免名单（理由都写在 data.py 的注释里）：
    #   get_shared_dashboard        —— 分享页凭 ShareToken 反查大屏（IsPublic=1 在函数内卡死）
    #   get_chart_for_shared_layout —— 分享页为布局取图表配置。只有 token 校验通过后才会
    #                                  走到这里；且下方"唯一引用点"检查把它锁死在分享路由，
    #                                  任何想在普通接口复用这条跨用户查询的行为都会亮红灯。
    ALLOWED_WITHOUT_USER = {"get_shared_dashboard", "get_chart_for_shared_layout"}
    offenders: list[str] = []
    checked = 0

    for name, fn in vars(data).items():
        if name.startswith("_") or not inspect.isfunction(fn):
            continue
        if fn.__module__ != data.__name__:
            continue
        checked += 1
        params = list(inspect.signature(fn).parameters)
        if name in ALLOWED_WITHOUT_USER:
            check(
                not params or params[0] != "user_id",
                f"静态：{name}() 是登记在册的刻意豁免（只读分享通道）",
            )
            continue
        if not params or params[0] != "user_id":
            offenders.append(f"{name}({', '.join(params)})")

    check(
        not offenders,
        f"静态：data.py 里全部 {checked} 个函数都以 user_id 作为第一个参数",
        ("漏网的函数：" + "；".join(offenders)) if offenders else "",
    )

    # 再扫一遍 SQL 文本：凡是查这三张表的语句，都得带隔离条件。
    #
    # 用共享的 _sqlscan 而不是自己写扫描 —— 这里踩过两次坑：
    #   1) 最初逐行扫描，跨行 SQL 会误报
    #   2) 改成只看 ast.Constant 后，**f-string 里的 SQL 完全看不见**
    #      （f-string 是 ast.JoinedStr），于是漏掉了 users.py 里写死的 LIMIT，
    #      直到连上真实 SQL Server 才炸出来
    from _sqlscan import scan_dialect_tokens, sql_strings

    app_dir = pathlib.Path(data.__file__).resolve().parent
    table_sql: list[str] = []
    table_sql_pairs: list[tuple[int, str]] = []
    for lineno, sql in sql_strings(data.__file__):
        if any(t in sql for t in ("FROM Datasets", "FROM Charts", "FROM Dashboards")):
            table_sql.append(sql)
            table_sql_pairs.append((lineno, sql))

    check(len(table_sql) >= 8, f"静态：解析到 {len(table_sql)} 条针对业务表的查询语句")

    # 计算"豁免函数"在 data.py 里占据的行区间：只有这些函数体内部的
    # 跨用户查询才免检。理由见上方 ALLOWED_WITHOUT_USER 注释。
    # —— 用行区间而非字符串匹配：既精准，又保证将来在别处乱写照样被抓。
    exempt_ranges: list[tuple[int, int]] = []
    for name in ALLOWED_WITHOUT_USER:
        fn = getattr(data, name, None)
        if fn is None:
            continue
        try:
            src_lines, start = inspect.getsourcelines(fn)
        except OSError:
            continue
        exempt_ranges.append((start, start + len(src_lines)))

    def _in_exempt(lineno: int) -> bool:
        return any(a <= lineno < b for a, b in exempt_ranges)

    missing_where = [
        f"L{lineno}: {s}"
        for lineno, s in table_sql_pairs
        if "UserID = ?" not in s
        and "ShareToken = ?" not in s
        and not _in_exempt(lineno)
    ]
    check(
        not missing_where,
        "静态：所有针对业务表的查询语句都带 UserID 条件（分享查询用 ShareToken，豁免函数按行区间放行）",
        ("可疑语句：" + " | ".join(missing_where)) if missing_where else "",
    )

    # 钉死豁免：跨用户读函数只能被分享路由引用，且全项目仅一处调用。
    # 谁想把它复用进普通接口（=真正的越权口子），引用计数立刻变 2 → 红灯。
    app_root = pathlib.Path(data.__file__).resolve().parents[1]
    refs: list[str] = []
    for py in sorted(app_root.rglob("*.py")):
        if py.name == "data.py":
            continue  # 定义本身不算引用
        for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if "get_chart_for_shared_layout" in line:
                refs.append(f"{py.name}:{lineno}")
    check(
        len(refs) == 1 and refs[0].startswith("dashboards.py"),
        "静态：get_chart_for_shared_layout 仅被分享路由引用（全项目唯一调用点）",
        f"引用处：{refs}",
    )

    # 防止将来有人又在 SQL 里写死某个数据库专有的写法（换库会直接报错）。
    #
    # 扫描范围是**整个 app 包**，不只是 data.py —— 因为 LIMIT 那次翻车
    # 就发生在 users.py 里，只扫 data.py 会漏掉。
    all_hits: list[tuple[str, str, int, str, str]] = []
    for py in sorted(app_dir.rglob("*.py")):
        for label, lineno, explanation, sql in scan_dialect_tokens(py):
            all_hits.append((py.name, label, lineno, explanation, sql))

    check(
        not all_hits,
        f"静态：整个后端代码里的 SQL 都没有写死数据库专有写法（共扫 {len(list(app_dir.rglob('*.py')))} 个文件）",
        (
            "发现可疑写法：\n           "
            + "\n           ".join(
                f"{fname}:{lineno} 用了 {label}（{explanation}）\n             → {sql[:110]}"
                for fname, label, lineno, explanation, sql in all_hits
            )
        )
        if all_hits
        else "",
    )

    # 扫描器自检：证明它**真的能**抓到东西。
    # 这一步很关键 —— 否则扫描器哪天坏了、什么都扫不到，
    # 上面那条检查会"因为没发现问题而通过"，变成一句空话。
    # 这里把一段故意违规的 SQL 写进临时文件，确认能被抓出来。
    import tempfile

    from _sqlscan import scan_dialect_tokens as _scan

    probe = pathlib.Path(tempfile.mkdtemp()) / "probe.py"
    probe.write_text(
        'def f(limit):\n'
        '    """这段文档字符串里提到 LIMIT 和 datetime(\'now\')，不应被误报。"""\n'
        '    return f"SELECT ID FROM T ORDER BY ID LIMIT {int(limit)}"\n'
        'BAD = "SELECT * FROM T WHERE T = datetime(\'now\')"\n'
        'GOOD = "SELECT * FROM T WHERE UserID = ?"\n',
        encoding="utf-8",
    )
    probe_hits = {label for label, *_ in _scan(probe)}
    check(
        "LIMIT" in probe_hits and "datetime('now')" in probe_hits,
        "静态：扫描器自检 —— 故意写的违规 SQL 能被抓出来（含 f-string 里的）",
        f"只抓到了 {probe_hits}",
    )
    check(
        probe_hits != {"TOP n"},
        "静态：扫描器能识别 f-string 里的 SQL（这是曾经漏掉 LIMIT 的原因）",
        f"抓到 {probe_hits}",
    )

    # 顺带确认：那唯一一条不按 UserID 过滤的语句，必须同时限定 IsPublic = 1
    share_sql = [s for s in table_sql if "ShareToken = ?" in s]
    check(
        len(share_sql) == 1 and "IsPublic = 1" in share_sql[0],
        "静态：只读分享查询同时限定了 IsPublic = 1（否则等于公开全部大屏）",
        f"实际：{share_sql}",
    )

    # ------------------------------------------------------- 善后与汇总
    print()
    print("─" * 78)
    print("善后：清理测试数据，确认没有留下垃圾")
    print("─" * 78)
    cleanup(verbose=True)
    leftover = []
    for name in TEST_USERNAMES:
        if users.find_by_username(name) is not None:
            leftover.append(name)
    check(not leftover, "测试账号已从数据库彻底删除", f"残留：{leftover}")

    if IS_REAL_DB:
        # 真实数据库上更要确认：除了原本就有的账号，没多出任何东西
        remaining = users.count_users()
        print(f"    当前库中剩余用户数：{remaining}（应为 1，即内置 demo 账号）")

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
    if IS_REAL_DB:
        print(f"运行环境：真实数据库 {settings.mssql_database}（pymssql 驱动）")
    else:
        print("运行环境：临时 SQLite")

    if passed == total:
        print("\n✅ 数据隔离验证通过：甲用户无法查看/修改/删除乙用户的任何数据。")
        return 0
    print(f"\n❌ 有 {total - passed} 项未通过，隔离存在漏洞，必须修复。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
