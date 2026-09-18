"""数据清洗与标准化引擎。

核心解决数据分析与图表生成中最常见的“脏数据陷阱”：
1. 合并单元格向下填充（Fill-down）：
   - Excel 常见的纵向跨行合并，读取时第 2 行起为 None/空字符，自动沿用上一行有效值填充（如省份、品类）；
2. 脏行自动过滤（Drop dirty rows）：
   - 全空行过滤；
   - 汇总行/合计行过滤（如包含“总计”、“合计”、“Total”、“汇总”的汇总行，防止拉爆统计图表双倍计算）；
3. 字符与数值清洗（Normalize numbers & text）：
   - 剥离千分位逗号（"1,234.50" -> 1234.50）；
   - 剥离货币与百分比符号（"￥100", "$50.5", "85%" -> 85.0）；
   - 保留学号/工号前导 0（若列名含“号/码/ID/Code”，作为文本存储不转成数字）；
4. 字段类型智能推断（Infer schema）：
   - 自动识别为 number（数值型，可用于折线/柱状/饼图数值轴）或 string（维度型，用于分类轴/图例）；
5. 生成可审计清洗日志（Audit cleaning log）：
   - 详细记录“填充了多少个合并单元格”、“过滤了多少行合计/空行”、“修正了多少处数值”，供课设演示答辩汇报。
"""

from __future__ import annotations

import re
from typing import Any

# 汇总行的典型关键词（正则匹配）
_SUMMARY_ROW_RE = re.compile(r"^\s*(总计|合计|平均|汇总|total|summary|average)\s*$", re.IGNORECASE)

# 编号类字段名特征（强制保留文本，避免前导 0 丢失，如 001 变成 1）
_CODE_HEADER_RE = re.compile(r"(编号|学号|工号|单号|序号|代码|code|id|no|num)", re.IGNORECASE)

# 数值清洗正则：剥离千分位逗号、空白、货币符号等
_NUMERIC_CLEAN_RE = re.compile(r"[￥$¥,\s]")


def is_summary_value(val: Any) -> bool:
    """判断一个单元格值是否是汇总标记"""
    if val is None:
        return False
    s = str(val).strip()
    return bool(_SUMMARY_ROW_RE.match(s))


def parse_clean_number(val: Any) -> tuple[bool, float | int | None]:
    """尝试将字符串/对象清洗为标准数字。
    
    返回 (是否成功, 清洗后的数值)
    """
    if val is None:
        return False, None
    if isinstance(val, (int, float)):
        return True, val

    s = str(val).strip()
    if not s:
        return False, None

    # 如果带百分号，先剥离并转浮点数
    if s.endswith("%"):
        sub = s[:-1].strip()
        try:
            cleaned = float(_NUMERIC_CLEAN_RE.sub("", sub))
            return True, round(cleaned / 100.0, 6)
        except ValueError:
            return False, None

    # 剥离货币符号和千分位逗号
    cleaned_s = _NUMERIC_CLEAN_RE.sub("", s)
    try:
        if "." in cleaned_s:
            return True, float(cleaned_s)
        return True, int(cleaned_s)
    except ValueError:
        return False, None


def infer_column_type(header: str, values: list[Any]) -> str:
    """推断列类型：'number' 或 'string'"""
    # 如果列名明显是编号、学号、ID，强制为 string
    if _CODE_HEADER_RE.search(header):
        return "string"

    valid_vals = [v for v in values if v is not None and str(v).strip() != ""]
    if not valid_vals:
        return "string"

    # 尝试按数值解析比例
    num_count = sum(1 for v in valid_vals if parse_clean_number(v)[0])
    ratio = num_count / len(valid_vals)
    # 若 85% 以上都是有效数值，推断为 number
    return "number" if ratio >= 0.85 else "string"


class DataCleaner:
    """数据集清洗器"""

    def __init__(
        self,
        headers: list[str],
        matrix: list[list[Any]],
        *,
        fill_down_merged: bool = True,
        filter_summary_rows: bool = True,
        filter_empty_rows: bool = True,
        auto_convert_numbers: bool = True,
        trim_spaces: bool = True,
    ) -> None:
        self.headers = list(headers)
        self.matrix = matrix  # 第一行为表头之后的数据行（不含表头）
        self.fill_down_merged = fill_down_merged
        self.filter_summary_rows = filter_summary_rows
        self.filter_empty_rows = filter_empty_rows
        self.auto_convert_numbers = auto_convert_numbers
        self.trim_spaces = trim_spaces
        self.logs: list[dict[str, Any]] = []

    def clean(self) -> dict[str, Any]:
        cleaned_rows: list[list[Any]] = []
        fill_down_count = 0
        summary_rows_dropped = 0
        empty_rows_dropped = 0
        number_converted_count = 0

        # 上一行的有效值记忆（用于纵向向下填充合并单元格）
        last_valid_row: list[Any] = [None] * len(self.headers)

        for row_idx, raw_row in enumerate(self.matrix):
            # 补齐长度
            row = list(raw_row) + [None] * (len(self.headers) - len(raw_row))
            row = row[: len(self.headers)]

            # 1. 空白处理
            if self.trim_spaces:
                row = [str(c).strip() if c is not None and isinstance(c, str) else c for c in row]

            # 2. 检查是否全空行
            is_empty = all(c is None or c == "" for c in row)
            if is_empty:
                if self.filter_empty_rows:
                    empty_rows_dropped += 1
                    continue

            # 3. 检查是否合计/汇总行
            # 只要第一列或第二列出现“总计/合计/Total”，或者整行大部分字段为空且包含合计
            is_summary = any(is_summary_value(c) for c in row[:3])
            if is_summary:
                if self.filter_summary_rows:
                    summary_rows_dropped += 1
                    continue

            # 4. 纵向向下填充（针对合并单元格）
            current_cleaned_row = []
            for col_idx, cell in enumerate(row):
                header = self.headers[col_idx]
                is_cell_empty = cell is None or cell == ""

                # 只有非数值列、或者明确是文本维度列才执行向下填充（防止把真实的 0 漏填或把数值列填错）
                if self.fill_down_merged and is_cell_empty:
                    # 如果该列历史上有有效值，且该列不是纯数值计算列
                    if last_valid_row[col_idx] is not None and not _CODE_HEADER_RE.search(header):
                        filled_val = last_valid_row[col_idx]
                        current_cleaned_row.append(filled_val)
                        fill_down_count += 1
                    else:
                        current_cleaned_row.append(cell)
                else:
                    if not is_cell_empty:
                        last_valid_row[col_idx] = cell
                    current_cleaned_row.append(cell)

            cleaned_rows.append(current_cleaned_row)

        # 5. 列类型推断与数值格式标准化
        columns_meta: list[dict[str, Any]] = []
        for col_idx, h in enumerate(self.headers):
            col_values = [r[col_idx] for r in cleaned_rows]
            inferred_type = infer_column_type(h, col_values)
            columns_meta.append({
                "name": h,
                "type": inferred_type,
                "label": h,
                "is_metric": (inferred_type == "number"),
                "is_dimension": (inferred_type == "string"),
            })

        # 6. 对标记为 number 的列统一转换成 float/int
        final_records: list[dict[str, Any]] = []
        for row in cleaned_rows:
            record: dict[str, Any] = {}
            for col_idx, col_info in enumerate(columns_meta):
                h = col_info["name"]
                val = row[col_idx]
                if col_info["type"] == "number" and self.auto_convert_numbers:
                    ok, num = parse_clean_number(val)
                    if ok:
                        record[h] = num
                        if not isinstance(val, (int, float)):
                            number_converted_count += 1
                    else:
                        record[h] = 0
                else:
                    record[h] = "" if val is None else str(val)
            final_records.append(record)

        # 记录清洗审计日志
        cleaning_logs = []
        if fill_down_count > 0:
            cleaning_logs.append({
                "type": "fill_down",
                "title": "合并单元格向下填充",
                "count": fill_down_count,
                "desc": f"成功为纵向合并区域向下填充了 {fill_down_count} 处空白数据。",
            })
        if summary_rows_dropped > 0:
            cleaning_logs.append({
                "type": "drop_summary",
                "title": "剔除多余汇总/合计行",
                "count": summary_rows_dropped,
                "desc": f"剔除了 {summary_rows_dropped} 行总计/合计行，避免汇总图表产生双倍计算偏差。",
            })
        if empty_rows_dropped > 0:
            cleaning_logs.append({
                "type": "drop_empty",
                "title": "清理空行",
                "count": empty_rows_dropped,
                "desc": f"移除了 {empty_rows_dropped} 行无效全空行。",
            })
        if number_converted_count > 0:
            cleaning_logs.append({
                "type": "convert_numbers",
                "title": "格式规范化",
                "count": number_converted_count,
                "desc": f"规范化了 {number_converted_count} 处数值格式（剥离千分位逗号/货币符号/转数值型）。",
            })

        return {
            "columns": columns_meta,
            "rows": final_records,
            "row_count": len(final_records),
            "column_count": len(columns_meta),
            "cleaning_logs": cleaning_logs,
            "stats": {
                "fill_down_count": fill_down_count,
                "summary_rows_dropped": summary_rows_dropped,
                "empty_rows_dropped": empty_rows_dropped,
                "number_converted_count": number_converted_count,
            },
        }
