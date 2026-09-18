#!/usr/bin/env python3
"""生成"故意做脏"的示例数据文件。

为什么要故意做脏？
    给老师演示时，上传一个完美文件说明不了任何问题。
    上传一个"跟真实教务/电商系统导出的一模一样脏"的文件，
    然后看到系统把它洗干净 —— 这才是有说服力的演示。

本脚本生成的每个文件都植入了**真实世界里常见的毛病**，
具体清单见同目录的 README.md。

运行：cd samples && ../backend/.venv/bin/python generate_samples.py
"""

from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

HERE = Path(__file__).resolve().parent

# 12 个月的省份销售数据（与前端示例大屏同一套口径，便于对照）
PROVINCES = ["广东", "江苏", "浙江", "山东", "河南", "四川", "福建", "湖北"]
CATEGORIES = ["数码家电", "服饰鞋包", "食品生鲜", "家居日用", "美妆个护"]
BASE = {"广东": 5200, "江苏": 4300, "浙江": 4100, "山东": 3300,
        "河南": 2600, "四川": 2400, "福建": 2200, "湖北": 1900}
SHARE = {"数码家电": 0.32, "服饰鞋包": 0.24, "食品生鲜": 0.18,
         "家居日用": 0.15, "美妆个护": 0.11}
SEASON = [0.88, 0.74, 0.95, 1.00, 1.08, 1.62, 0.98, 1.02, 1.12, 1.20, 2.18, 1.48]


def clean_rows() -> list[dict]:
    """一份"干净"的基础数据，脏数据都是从它变形出来的。"""
    rows = []
    n = 0
    for prov in PROVINCES:
        for cat in CATEGORIES:
            for month in range(1, 13):
                n += 1
                amount = BASE[prov] * SHARE[cat] * SEASON[month - 1]
                rows.append(
                    {
                        "订单编号": f"SO{month:02d}{n:05d}",
                        "省份": prov,
                        "品类": cat,
                        "月份": month,
                        "销售额": round(amount, 2),
                        "订单量": max(1, round(amount * 10000 / 268)),
                    }
                )
    return rows


# ============================================================ 干净参考文件
def write_clean_csv(rows: list[dict]) -> None:
    path = HERE / "电商销售_干净数据.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  已生成 {path.name}（UTF-8，干净可直接用，{len(rows)} 行）")


# ==================================================== 脏示例 1：乱编码 CSV
def write_dirty_gbk_csv(rows: list[dict]) -> None:
    """植入问题：GBK 编码、带千分位逗号的文本数字、全角数字、空行、缺值、合计行。"""
    path = HERE / "电商销售_脏数据_GBK乱码.csv"
    with path.open("w", encoding="gbk", newline="") as f:
        w = csv.writer(f)
        w.writerow(["订单编号", "省份", "品类", "月份", "销售额", "订单量"])
        for i, r in enumerate(rows):
            amount = r["销售额"]
            orders = str(r["订单量"])
            if i % 7 == 3:
                amount = ""  # 缺失值
            elif i % 11 == 5:
                amount = f"{amount:,.2f}"  # 数字被写成带千分位的文本
            elif i % 13 == 7:
                orders = orders.translate(str.maketrans("0123456789", "０１２３４５６７８９"))  # 全角
            w.writerow([r["订单编号"], r["省份"], r["品类"], r["月份"], amount, orders])
            if i % 20 == 19:
                w.writerow([])  # 空行
        # 报表末尾的合计行：真实文件几乎都有，会污染数据
        w.writerow(["合计", "", "", "", f"{sum(r['销售额'] for r in rows):,.2f}", ""])
    print(f"  已生成 {path.name}（GBK 编码，含 6 类毛病）")


# ================================================= 脏示例 2：花式 Excel
def write_dirty_xlsx(rows: list[dict]) -> None:
    """植入问题：合并大标题、空行、真表头在第 3 行、省份列纵向合并（只有首行有值）、
    月份写成文本、缺失值、多余备注列、表尾制表人行、还有第二个工作表。"""
    wb = Workbook()

    ws = wb.active
    ws.title = "1月-12月明细"

    # 第 1 行：大标题，并横向合并 A1:F1 —— 解析时这里会整行错位
    ws["A1"] = "华东华南区电商销售明细表（2024 年度）"
    ws["A1"].font = Font(bold=True, size=14)
    ws.merge_cells("A1:F1")

    # 第 2 行留空；真正的表头在第 3 行
    headers = ["订单编号", "省份", "品类", "月份", "销售额", "订单量", "备注"]
    for col, name in enumerate(headers, start=1):
        ws.cell(row=3, column=col, value=name).font = Font(bold=True)

    # ---------- 先按顺序铺数据，同时记下每一行对应的省份 ----------
    entries: list[dict | None] = []
    for i, r in enumerate(rows):
        amount = r["销售额"]
        if i % 9 == 2:
            amount = None  # 缺失值
        entries.append(
            {
                "订单编号": r["订单编号"],
                "省份": r["省份"],
                "品类": r["品类"],
                "月份": f"2024年{r['月份']}月",  # 月份是文本而不是数字
                "销售额": amount,
                "订单量": r["订单量"],
            }
        )
        if i % 25 == 24:
            entries.append(None)  # 每隔一段插一个空行

    start_row = 4
    province_rows: list[tuple[str, int, int]] = []  # (省份, 起始行, 结束行)
    prev_prov = None

    for idx, entry in enumerate(entries):
        excel_row = start_row + idx
        if entry is None:
            prev_prov = None  # 空行会打断合并区间（真实文件也是如此）
            continue
        if entry["省份"] == prev_prov:
            province_rows[-1] = (prev_prov, province_rows[-1][1], excel_row)
        else:
            province_rows.append((entry["省份"], excel_row, excel_row))
        prev_prov = entry["省份"]

    # 写入单元格：属于合并区间的行，只有首行写省份，其余留空
    first_rows = {rng[1] for rng in province_rows}
    for idx, entry in enumerate(entries):
        excel_row = start_row + idx
        if entry is None:
            continue
        for col, key in enumerate(["订单编号", "省份", "品类", "月份", "销售额", "订单量"], start=1):
            value = entry[key]
            if key == "省份" and excel_row not in first_rows:
                value = None  # 被合并"吃掉"的省份
            ws.cell(row=excel_row, column=col, value=value)

    # 真正执行纵向合并（只保留左上角的值）
    for prov, r1, r2 in province_rows:
        if r2 > r1:
            ws.merge_cells(start_row=r1, start_column=2, end_row=r2, end_column=2)

    # 零散的备注
    ws.cell(row=4, column=7, value="含赠品")
    ws.cell(row=9, column=7, value="退货1单")

    # 表尾的"制表人"行：解析时必须丢弃
    last_row = start_row + len(entries)
    ws.cell(row=last_row + 1, column=1, value="制表人：张三    制表日期：2025-01-08")

    # 第二个工作表
    ws2 = wb.create_sheet("说明")
    ws2["A1"] = "本表为演示用脏数据，请勿用于真实业务。"
    ws2["A2"] = "数据来源：课设演示样本"

    path = HERE / "电商销售_脏数据_Excel花式.xlsx"
    wb.save(path)
    merged = sum(1 for _, r1, r2 in province_rows if r2 > r1)
    print(f"  已生成 {path.name}（合并标题 + 表头错位 + {merged} 处省份纵向合并 + 空行 + 缺失值 + 第二工作表）")


# ============================================ 脏示例 3：编号丢前导零
def write_dirty_ids_csv(rows: list[dict]) -> None:
    """植入问题：编号前导 0 丢失、省份夹杂空格、重复表头行。"""
    path = HERE / "电商销售_脏数据_编号丢零.csv"
    subset = rows[:60]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["学生编号", "省份", "品类", "销售额"])
        for i, r in enumerate(subset):
            sid = int(f"20230{i:04d}")  # 以数字形式写出，前导 0 会丢
            prov = r["省份"]
            if i % 6 == 1:
                prov = prov.replace("广", "广 ")  # 夹杂空格
            w.writerow([sid, prov, r["品类"], r["销售额"]])
            if i % 15 == 14:
                w.writerow(["学生编号", "省份", "品类", "销售额"])  # 又插一遍表头
    print(f"  已生成 {path.name}（前导 0 丢失 + 重复表头 + 空格污染）")


def main() -> None:
    print("正在生成示例数据文件…")
    rows = clean_rows()
    write_clean_csv(rows)
    write_dirty_gbk_csv(rows)
    write_dirty_xlsx(rows)
    write_dirty_ids_csv(rows)
    print(f"\n全部完成，输出目录：{HERE}")


if __name__ == "__main__":
    main()
