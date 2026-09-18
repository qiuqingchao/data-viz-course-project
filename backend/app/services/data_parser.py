"""文件解析与嗅探服务（纯内存流处理，不向磁盘落盘未处理文件）。

处理逻辑：
1. 编码检测（CSV）：
   - 使用 chardet 抽样检测字符编码，针对 GBK、GB18030、UTF-8、UTF-8-SIG(BOM) 做智能容错。
2. CSV 流式解析：
   - 使用标准库 csv.reader，自动嗅探或兼容各种分隔符（逗号、制表符、分号）。
3. Excel 解析（.xlsx / .xls）：
   - 使用 openpyxl 模式读取；
   - 提取所有工作表 (sheets) 列表；
   - 默认解析第一个工作表或指定工作表；
   - 保留合并单元格原始样貌（或标注合并区域），便于后续清洗步填补；
4. 预览与元信息提取：
   - 提取列名、字段数、总行数（估算/精确）；
   - 提取前 N 行原始数据预览。
"""

from __future__ import annotations

import csv
import io
from typing import Any

import chardet
import openpyxl

from app.config import settings


class DataParseError(Exception):
    """解析失败时抛出友好错误提示"""
    pass


def detect_encoding(raw_bytes: bytes) -> str:
    """自动探测文件编码，优先处理 UTF-8 BOM 和常见中文编码"""
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    
    # 取前 64KB 做嗅探，提升效率
    sample = raw_bytes[:65536]
    detected = chardet.detect(sample)
    encoding = (detected.get("encoding") or "utf-8").lower()
    
    # 针对 Windows 常见的 GB2312 / GBK 统一向上兼容到 GB18030
    if encoding in ("gb2312", "gbk"):
        encoding = "gb18030"
    elif encoding in ("ascii", "utf-8"):
        # 验证是否真的能用 utf-8 解码完整样本
        try:
            sample.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            encoding = "gb18030"
            
    return encoding


def parse_csv_preview(
    raw_bytes: bytes,
    preview_limit: int = 20,
) -> dict[str, Any]:
    """解析 CSV 文件并返回预览与元数据"""
    encoding = detect_encoding(raw_bytes)
    
    try:
        text = raw_bytes.decode(encoding)
    except Exception as e:
        # 如果当前编码解码失败，尝试用 GB18030 兜底
        try:
            encoding = "gb18030"
            text = raw_bytes.decode("gb18030", errors="replace")
        except Exception:
            raise DataParseError(f"文件编码解析失败（检测编码为 {encoding}）: {e}") from e

    # 简单过滤首尾空白行
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise DataParseError("CSV 文件内容为空")

    # 尝试嗅探分隔符
    sample_text = "\n".join(lines[:10])
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters=[",", "\t", ";", "|"])
        delimiter = dialect.delimiter
    except Exception:
        delimiter = ","

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    all_rows: list[list[str]] = []
    max_cols = 0
    
    for row_idx, row in enumerate(reader):
        if row_idx >= settings.max_rows + 10:  # 超过上限截断
            break
        # 去除单元格多余空格
        cleaned_row = [cell.strip() for cell in row]
        all_rows.append(cleaned_row)
        if len(cleaned_row) > max_cols:
            max_cols = len(cleaned_row)

    if not all_rows:
        raise DataParseError("未能在 CSV 中读取到有效数据行")

    if max_cols > settings.max_columns:
        raise DataParseError(f"列数过多（{max_cols} 列），当前系统最多支持 {settings.max_columns} 列")

    total_rows = len(all_rows)
    # 取第一行作为表头候选
    raw_headers = all_rows[0]
    # 构造规范列名：如果某列没有列名，赋予自动命名 Col_1, Col_2...
    headers: list[str] = []
    for idx in range(max_cols):
        h = raw_headers[idx] if idx < len(raw_headers) and raw_headers[idx] else f"Col_{idx + 1}"
        # 避免重名列
        orig_h = h
        counter = 1
        while h in headers:
            h = f"{orig_h}_{counter}"
            counter += 1
        headers.append(h)

    # 预览数据行（最多 preview_limit 行，不包含表头自身）
    preview_rows_data = all_rows[1 : preview_limit + 1]
    preview_records: list[dict[str, Any]] = []
    for r in preview_rows_data:
        record: dict[str, Any] = {}
        for c_idx, h in enumerate(headers):
            val = r[c_idx] if c_idx < len(r) else ""
            record[h] = val
        preview_records.append(record)

    return {
        "file_type": "csv",
        "encoding": encoding,
        "delimiter": delimiter,
        "total_rows": total_rows - 1,  # 排除表头后的有效数据行数
        "total_columns": max_cols,
        "headers": headers,
        "preview_rows": preview_records,
        "raw_preview_matrix": all_rows[: preview_limit + 1],
        # 全量矩阵（含表头行，已受 MAX_ROWS=5000 护栏截断）：
        # 清洗与入库都吃这个。曾经只回传预览 20 行，导致"界面显示 480 行、库里只存 20 行"
        "raw_matrix": all_rows,
        "sheets": [],
        "current_sheet": None,
    }


def parse_excel_preview(
    raw_bytes: bytes,
    sheet_name: str | None = None,
    preview_limit: int = 20,
) -> dict[str, Any]:
    """解析 Excel 文件 (.xlsx) 并返回预览与元数据"""
    try:
        wb = openpyxl.load_workbook(
            filename=io.BytesIO(raw_bytes),
            read_only=False,  # read_only=False 才能精确获取 merged_cells
            data_only=True,   # 读取公式求值后的结果而非公式表达式
        )
    except Exception as e:
        raise DataParseError(f"Excel 文件无法解析（请确认是否为有效的 .xlsx 格式）: {e}") from e

    sheet_names = wb.sheetnames
    if not sheet_names:
        raise DataParseError("Excel 文件中未发现任何工作表 (Sheet)")

    # 选定 sheet
    target_sheet = sheet_name if sheet_name in sheet_names else sheet_names[0]
    ws = wb[target_sheet]

    # 检测合并单元格信息（用于提醒用户及后续清洗填补）
    merged_ranges_info: list[str] = []
    for rng in ws.merged_cells.ranges:
        merged_ranges_info.append(str(rng))

    # 读取所有行数据
    raw_matrix: list[list[Any]] = []
    max_cols = 0
    row_count = 0

    for row in ws.iter_rows(values_only=True):
        # 如果整行都是 None 则忽略尾部空行
        if all(cell is None or str(cell).strip() == "" for cell in row):
            if row_count > 0:
                raw_matrix.append(["" for _ in range(max_cols)])
            continue
        
        row_count += 1
        if row_count > settings.max_rows + 10:
            break

        str_row: list[str] = []
        for cell in row:
            if cell is None:
                str_row.append("")
            else:
                str_row.append(str(cell).strip())
        raw_matrix.append(str_row)
        if len(str_row) > max_cols:
            max_cols = len(str_row)

    wb.close()

    if not raw_matrix:
        raise DataParseError(f"工作表「{target_sheet}」中未包含有效数据")

    if max_cols > settings.max_columns:
        raise DataParseError(f"工作表列数过多（{max_cols} 列），系统上限为 {settings.max_columns} 列")

    # 简单提取表头候选行（第一行非空行）
    headers: list[str] = []
    first_row = raw_matrix[0]
    for idx in range(max_cols):
        val = first_row[idx] if idx < len(first_row) and first_row[idx] else f"Col_{idx + 1}"
        orig_val = val
        c = 1
        while val in headers:
            val = f"{orig_val}_{c}"
            c += 1
        headers.append(val)

    # 构造预览行对象
    preview_data = raw_matrix[1 : preview_limit + 1]
    preview_records: list[dict[str, Any]] = []
    for r in preview_data:
        record: dict[str, Any] = {}
        for c_idx, h in enumerate(headers):
            cell_val = r[c_idx] if c_idx < len(r) else ""
            record[h] = cell_val
        preview_records.append(record)

    return {
        "file_type": "excel",
        "encoding": "utf-8",
        "delimiter": None,
        "sheets": sheet_names,
        "current_sheet": target_sheet,
        "merged_cells_count": len(merged_ranges_info),
        "merged_ranges": merged_ranges_info[:10],  # 仅带出前10个合并区域作为展示
        "total_rows": max(0, row_count - 1),
        "total_columns": max_cols,
        "headers": headers,
        "preview_rows": preview_records,
        "raw_preview_matrix": raw_matrix[: preview_limit + 1],
        # 全量矩阵（含表头行，已受 MAX_ROWS 护栏截断）：清洗与入库都吃这个，
        # 与 CSV 分支保持一致，避免"预览 20 行 = 入库 20 行"的数据丢失
        "raw_matrix": raw_matrix,
    }


def parse_dataset_file(
    file_bytes: bytes,
    filename: str,
    sheet_name: str | None = None,
    preview_limit: int = 20,
) -> dict[str, Any]:
    """主入口函数：根据扩展名与内容分发解析"""
    if not file_bytes:
        raise DataParseError("上传的文件为空文件（0 字节）")

    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > settings.max_upload_mb:
        raise DataParseError(
            f"文件大小超出限制：当前为 {size_mb:.2f} MB，系统最大支持 {settings.max_upload_mb} MB"
        )

    lower_name = filename.lower()
    if lower_name.endswith(".csv") or lower_name.endswith(".txt"):
        return parse_csv_preview(file_bytes, preview_limit=preview_limit)
    elif lower_name.endswith(".xlsx"):
        return parse_excel_preview(file_bytes, sheet_name=sheet_name, preview_limit=preview_limit)
    elif lower_name.endswith(".xls"):
        raise DataParseError("暂不支持旧版 .xls 二进制格式，请在 Excel 中另存为 .xlsx 或 .csv 格式后上传")
    else:
        # 尝试通过内容嗅探
        if file_bytes.startswith(b"PK\x03\x04"):  # Zip/XLSX 魔数
            return parse_excel_preview(file_bytes, sheet_name=sheet_name, preview_limit=preview_limit)
        else:
            # 兜底按 CSV 解析
            return parse_csv_preview(file_bytes, preview_limit=preview_limit)
