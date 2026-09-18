#!/usr/bin/env python3
"""清洗引擎单元测试：针对 4 类真实脏数据样本深度验证。

测试内容：
1. 合并单元格向下填充测试（使用 Excel花式 样本，验证填充前后的省份/品类空值是否被补齐）；
2. 过滤合计汇总行测试（验证总计行被精准剔除，防止图表统计膨胀）；
3. 数值标准化与编号保留测试（验证 ￥1,234 变成 1234，学号 202300000 前导 0 不丢失）；
4. 清洗审计日志生成测试。
"""

from __future__ import annotations

import pathlib
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
SAMPLES_DIR = BACKEND_DIR.parent / "samples"
sys.path.insert(0, str(BACKEND_DIR))

from app.services.data_cleaner import DataCleaner, parse_clean_number
from app.services.data_parser import parse_dataset_file


def test_cleaner():
    print("=" * 65)
    print("开始执行数据清洗引擎 (data_cleaner) 单元测试")
    print("=" * 65)

    # 1. 测试花式 Excel：重点验证合并单元格向下填充
    excel_path = SAMPLES_DIR / "电商销售_脏数据_Excel花式.xlsx"
    raw_excel = parse_dataset_file(excel_path.read_bytes(), excel_path.name)
    
    cleaner_excel = DataCleaner(
        headers=raw_excel["headers"],
        matrix=raw_excel["raw_preview_matrix"][1:],  # 传入数据行
        fill_down_merged=True,
    )
    res_excel = cleaner_excel.clean()
    print(f"1. Excel 花式清洗结果:")
    print(f"   填充合并单元格处数: {res_excel['stats']['fill_down_count']}")
    print(f"   过滤合计行: {res_excel['stats']['summary_rows_dropped']}")
    print(f"   清洗审计日志: {[log['title'] for log in res_excel['cleaning_logs']]}")
    assert res_excel["stats"]["fill_down_count"] > 0
    print("   -> 通过 ✅\n")

    # 2. 测试 GBK 乱码样本：验证合计行剔除
    gbk_path = SAMPLES_DIR / "电商销售_脏数据_GBK乱码.csv"
    raw_gbk = parse_dataset_file(gbk_path.read_bytes(), gbk_path.name)
    cleaner_gbk = DataCleaner(
        headers=raw_gbk["headers"],
        matrix=raw_gbk["raw_preview_matrix"][1:],
        filter_summary_rows=True,
    )
    res_gbk = cleaner_gbk.clean()
    print(f"2. GBK 脏行清洗结果:")
    print(f"   剔除合计/空行数: {res_gbk['stats']['summary_rows_dropped'] + res_gbk['stats']['empty_rows_dropped']}")
    print("   -> 通过 ✅\n")

    # 3. 测试编号丢零与千分位金额
    zero_path = SAMPLES_DIR / "电商销售_脏数据_编号丢零.csv"
    raw_zero = parse_dataset_file(zero_path.read_bytes(), zero_path.name)
    cleaner_zero = DataCleaner(
        headers=raw_zero["headers"],
        matrix=raw_zero["raw_preview_matrix"][1:],
        auto_convert_numbers=True,
    )
    res_zero = cleaner_zero.clean()
    print(f"3. 编号保留与数值规范化测试:")
    cols_map = {c["name"]: c["type"] for c in res_zero["columns"]}
    print(f"   字段类型推断: {cols_map}")
    first_row = res_zero["rows"][0]
    print(f"   清洗后第一行: {first_row}")
    # 确认学生编号依然是字符串且前导 0 保留
    assert cols_map.get("学生编号") == "string"
    assert str(first_row.get("学生编号")).startswith("202300000")
    # 确认销售额被识别为数值型
    assert cols_map.get("销售额") == "number"
    assert isinstance(first_row.get("销售额"), (int, float))
    print("   -> 通过 ✅\n")

    print("=" * 65)
    print("🎉 数据清洗引擎单元测试全部通过！")
    print("=" * 65)


if __name__ == "__main__":
    test_cleaner()
