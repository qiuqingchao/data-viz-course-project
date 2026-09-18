"""四张业务表的建表语句（两种数据库各一份）。

表结构设计说明（写在这里，免得将来忘了为什么这么设计）：

Users（用户）
    密码**只存加密后的乱码**，不存明文。字段叫 PasswordHash，
    格式形如 scrypt$n=16384,r=8,p=1$盐$哈希，盐和参数都写在里面，
    将来想换更强的算法也认得出来。

Datasets（数据集）
    用户上传并清洗后的数据。**不保存原始文件**（省磁盘、也少一份隐私风险），
    只保存解析后的数据（DataJson）和"做过哪些清洗"的配方（CleaningLogJson）。
    DataJson 是一大坨 JSON，所以它**只能整取整存，不能用 SQL 查询**——
    这一点在 README 里会如实写明。

Charts（图表）
    ConfigJson 存 ECharts 的配置。绑定的 DatasetID 记录数据来源。

Dashboards（大屏）
    LayoutJson 存每个面板的位置和尺寸。ShareToken 用于第 6 阶段的
    "只读分享链接"（可为空，为空表示没开启分享）。

关于唯一索引（踩过的坑）：
    ShareToken 上不能建**不带条件**的唯一索引。SQL Server 会把多个 NULL
    当成重复值，导致"表里只能有一个大屏"——第二条数据一插入就报
    `Cannot insert duplicate key ... The duplicate key value is (<NULL>)`。
    SQLite 和 PostgreSQL 允许多个 NULL，所以本地怎么测都正常。
    正确写法是带过滤条件：WHERE ShareToken IS NOT NULL。

关于命名（踩过的坑）：
    列名 **不能用 `RowCount`** —— `ROWCOUNT` 是 SQL Server 的保留字，
    直接写会报 `Incorrect syntax near the keyword 'RowCount'`。
    这里改名为 `RowTotal`，而不是给它加方括号 `[RowCount]`：
    加方括号需要在**每一处引用**都记得加，漏一处就是运行时错误；
    换个不撞保留字的名字，则永远不需要特殊照顾。
    为防止以后再撞，tests/test_schema_portability.py 会拿真实 SQL Server
    逐个验证所有标识符（没有数据库时退回内置保留字表）。

关于可移植性（踩过的坑）：
    `CREATE TABLE IF NOT EXISTS` 是 SQLite / MySQL 的语法，**SQL Server 不认识**；
    索引也一样没有 `IF NOT EXISTS`。所以这里不写那种语法，
    改成"先问数据库这个表/索引在不在，不在才建"——
    判断语句由方言提供，业务代码不用关心差异。
"""

from __future__ import annotations

from .dialect import Dialect, current_dialect


def _tables(d: Dialect) -> list[tuple[str, str]]:
    """返回 [(表名, 建表语句), ...]，语句里不含 IF NOT EXISTS。"""
    pk = d.autoincrement_pk()
    txt = d.text
    dt = d.datetime_type()
    bit = d.bit_type()
    now = d.now_expr()
    inty = d.int_type()

    return [
        (
            "Users",
            f"""
            CREATE TABLE Users (
                UserID        {pk},
                Username      {txt(64)}  NOT NULL,
                PasswordHash  {txt(255)} NOT NULL,
                DisplayName   {txt(64)},
                Role          {txt(16)}  NOT NULL DEFAULT 'student',
                IsActive      {bit}      NOT NULL DEFAULT 1,
                CreatedAt     {dt}       NOT NULL DEFAULT ({now}),
                LastLoginAt   {dt}
            )
            """,
        ),
        (
            "Datasets",
            f"""
            CREATE TABLE Datasets (
                DatasetID        {pk},
                UserID           {inty}  NOT NULL,
                Name             {txt(128)} NOT NULL,
                SourceFileName   {txt(255)},
                SourceSheet      {txt(128)},
                RowTotal         {inty}  NOT NULL DEFAULT 0,
                ColumnCount      {inty}  NOT NULL DEFAULT 0,
                ColumnsJson      {txt()}  NOT NULL,
                DataJson         {txt()}  NOT NULL,
                CleaningLogJson  {txt()},
                CreatedAt        {dt}     NOT NULL DEFAULT ({now}),
                UpdatedAt        {dt},
                FOREIGN KEY (UserID) REFERENCES Users (UserID)
            )
            """,
        ),
        (
            "Charts",
            f"""
            CREATE TABLE Charts (
                ChartID      {pk},
                UserID       {inty}  NOT NULL,
                DatasetID    {inty},
                Title        {txt(128)} NOT NULL,
                ChartType    {txt(32)}  NOT NULL,
                ConfigJson   {txt()}    NOT NULL,
                CreatedAt    {dt}       NOT NULL DEFAULT ({now}),
                UpdatedAt    {dt},
                FOREIGN KEY (UserID) REFERENCES Users (UserID),
                FOREIGN KEY (DatasetID) REFERENCES Datasets (DatasetID)
            )
            """,
        ),
        (
            "Dashboards",
            f"""
            CREATE TABLE Dashboards (
                DashboardID  {pk},
                UserID       {inty}  NOT NULL,
                Title        {txt(128)} NOT NULL,
                LayoutJson   {txt()}    NOT NULL,
                ShareToken   {txt(64)},
                IsPublic     {bit}      NOT NULL DEFAULT 0,
                CreatedAt    {dt}       NOT NULL DEFAULT ({now}),
                UpdatedAt    {dt},
                FOREIGN KEY (UserID) REFERENCES Users (UserID)
            )
            """,
        ),
    ]


def _indexes(d: Dialect) -> list[tuple[str, str]]:
    """返回 [(索引名, 建索引语句), ...]。"""
    return [
        ("ux_users_username", "CREATE UNIQUE INDEX ux_users_username ON Users (Username)"),
        ("ix_datasets_user", "CREATE INDEX ix_datasets_user ON Datasets (UserID)"),
        ("ix_charts_user", "CREATE INDEX ix_charts_user ON Charts (UserID)"),
        ("ix_dashboards_user", "CREATE INDEX ix_dashboards_user ON Dashboards (UserID)"),
        (
            # 必须带 WHERE ShareToken IS NOT NULL —— 否则在 SQL Server 上
            # 会限制"整个表只能有一行 ShareToken 为 NULL"，也就是
            # **只能存在一个大屏**，第二条插入就报 duplicate key。
            # 原因是 SQL Server 的唯一索引把 NULL 当成一个普通值来判重，
            # 而 SQLite / PostgreSQL 允许多个 NULL。
            # 加过滤条件后，防重只作用于"真正开启了分享的大屏"，语义也更准确。
            "ux_dashboards_token",
            "CREATE UNIQUE INDEX ux_dashboards_token ON Dashboards (ShareToken) "
            "WHERE ShareToken IS NOT NULL",
        ),
    ]


def table_definitions(dialect: Dialect | None = None) -> list[tuple[str, str]]:
    return _tables(dialect or current_dialect())


def index_definitions(dialect: Dialect | None = None) -> list[tuple[str, str]]:
    return _indexes(dialect or current_dialect())


def preview_sql(db_mode: str = "sqlite") -> str:
    """把建表语句拼成一段可读 SQL，便于人工核对（不执行）。"""
    from .dialect import MSSQLDialect, SQLiteDialect

    d = MSSQLDialect() if db_mode == "mssql" else SQLiteDialect()
    parts = [s.strip() for _, s in _tables(d)]
    parts += [s for _, s in _indexes(d)]
    return ";\n\n".join(parts) + ";"
