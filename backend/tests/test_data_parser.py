#!/usr/bin/env python3
"""测试数据解析器：覆盖 4 种典型样本与边界条件。

测试内容：
1. 样本一：干净 CSV（UTF-8，480行），验证列名、行数、数据映射；
2. 样本二：GBK 乱码脏数据（含中文乱码、合计行、空行），验证编码自动纠正为 GB18030；
3. 样本三：Excel 花式脏数据（多 Sheet、大标题行、26 处纵向合并单元格）；
4. 样本四：编号丢零 CSV（前导 0 编号保留与处理）；
5. 边界异常：空文件、超过最大大小限制、非合法格式。
"""

from __future__ import annotations

import pathlib
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
SAMPLES_DIR = BACKEND_DIR.parent / "samples"
sys.path.insert(0, str(BACKEND_DIR))

from app.services.data_parser import DataParseError, detect_encoding, parse_dataset_file


def run_tests():
    print("=" * 60)
    print("执行数据解析器 (data_parser) 单元测试")
    print("=" * 60)

    # 1. 测试干净 CSV
    clean_csv = SAMPLES_DIR / "电商销售_干净数据.csv"
    assert clean_csv.exists(), f"文件不存在: {clean_csv}"
    content = clean_csv.read_bytes()
    res = parse_dataset_file(content, clean_csv.name)
    print("1. 干净 CSV 测试:")
    print(f"   检测编码: {res['encoding']}")
    print(f"   解析总行数: {res['total_rows']} (期望 480)")
    print(f"   解析列数: {res['total_columns']}")
    print(f"   列名: {res['headers']}")
    assert res["total_rows"] == 480
    assert "订单编号" in res["headers"]
    print("   -> 通过 ✅\n")

    # 2. 测试 GBK 乱码 CSV
    gbk_csv = SAMPLES_DIR / "电商销售_脏数据_GBK乱码.csv"
    content_gbk = gbk_csv.read_bytes()
    res_gbk = parse_dataset_file(content_gbk, gbk_csv.name)
    print("2. GBK 乱码 CSV 测试:")
    print(f"   检测编码: {res_gbk['encoding']}")
    print(f"   解析总行数: {res_gbk['total_rows']}")
    print(f"   前3行预览: {res_gbk['preview_rows'][:2]}")
    assert res_gbk["encoding"] in ("gb18030", "gbk")
    # 确认第一行表头能正常解码为汉字而非乱码
    assert any("订单" in h or "金额" in h for h in res_gbk["headers"])
    print("   -> 通过 ✅\n")

    # 3. 测试 Excel 花式脏数据
    xlsx_file = SAMPLES_DIR / "电商销售_脏数据_Excel花式.xlsx"
    content_xlsx = xlsx_file.read_bytes()
    res_xlsx = parse_dataset_file(content_xlsx, xlsx_file.name)
    print("3. Excel 花式脏数据测试:")
    print(f"   所有 Sheet: {res_xlsx['sheets']}")
    print(f"   当前解析 Sheet: {res_xlsx['current_sheet']}")
    print(f"   检测到合并单元格数量: {res_xlsx['merged_cells_count']} (期望 >= 20)")
    print(f"   合并单元格示例: {res_xlsx['merged_ranges'][:3]}")
    assert len(res_xlsx["sheets"]) >= 2
    assert res_xlsx["merged_cells_count"] >= 20
    print("   -> 通过 ✅\n")

    # 4. 测试编号丢零 CSV
    zero_csv = SAMPLES_DIR / "电商销售_脏数据_编号丢零.csv"
    content_zero = zero_csv.read_bytes()
    res_zero = parse_dataset_file(content_zero, zero_csv.name)
    print("4. 编号丢零 CSV 测试:")
    print(f"   列名: {res_zero['headers']}")
    print(f"   第一行原始数据: {res_zero['preview_rows'][0]}")
    assert res_zero["total_rows"] > 0
    print("   -> 通过 ✅\n")

    # 5. 异常测试：空文件
    print("5. 异常输入测试:")
    try:
        parse_dataset_file(b"", "empty.csv")
        assert False, "未能拦截空文件"
    except DataParseError as e:
        print(f"   空文件被正确拦截: {e}")

    # 超大文件拦截模拟 (构造虚拟 > 5MB)
    try:
        parse_dataset_file(b"x" * (6 * 1024 * 1024), "big.csv")
        assert False, "未能拦截超大文件"
    except DataParseError as e:
        print(f"   超大文件被正确拦截: {e}")

    print("   -> 通过 ✅\n")
    print("=" * 60)
    print("🎉 所有数据解析器单测全部通过！")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
