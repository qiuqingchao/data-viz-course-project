"""数据集与数据处理 API 路由。

提供核心功能：
1. GET  /api/datasets/samples —— 获取内置的测试样本文件列表；
2. POST /api/datasets/preview-sample —— 一键直接预览某个内置样本；
3. POST /api/datasets/preview —— 接收用户真实文件流上传并返回智能解析结果与前 20 行预览；
4. POST /api/datasets/preview-sheet —— 针对多工作表 Excel 切换工作表并重新提取预览；
5. POST /api/datasets/clean-preview —— 对当前表格根据自定义清洗规则执行试算并返回清洗前后对照；
6. POST /api/datasets/save —— 将清洗确认后的数据集正式持久化写入数据库 Datasets 表。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.config import settings
from app.db import data as db_data
from app.services.data_cleaner import DataCleaner
from app.services.data_parser import DataParseError, parse_dataset_file

router = APIRouter(prefix="/api/datasets", tags=["数据集与数据处理"])

SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "samples"

SAMPLE_META = {
    "电商销售_干净数据.csv": {
        "title": "干净数据（480行完整销售单）",
        "badge": "标准基线",
        "description": "UTF-8 编码，包含订单编号、省份、品类、月份、销售额、订单量等字段，无缺失。",
    },
    "电商销售_脏数据_GBK乱码.csv": {
        "title": "GBK 乱码与脏行（Windows 导出典型）",
        "badge": "乱码/多余行",
        "description": "GBK/GB18030 中文字符集，包含尾部合计汇总行与多余空行，用于测试自动编码检测。",
    },
    "电商销售_脏数据_Excel花式.xlsx": {
        "title": "花式 Excel（多 Sheet + 26 处合并单元格）",
        "badge": "合并单元格陷阱",
        "description": "含大标题行、多级工作表、纵向跨行合并单元格（传统工具导入会丢失下半部省份名）。",
    },
    "电商销售_脏数据_编号丢零.csv": {
        "title": "编号丢零与脏数字（学号/订单号典型）",
        "badge": "格式丢失",
        "description": "前导 0 学号/工号被数字类型误吞（001 变成 1）、带千分位逗号金额、带货币符号 ￥。",
    },
}


class SamplePreviewRequest(BaseModel):
    filename: str
    sheet_name: str | None = None


class CleanPreviewRequest(BaseModel):
    headers: list[str]
    raw_matrix: list[list[Any]]
    fill_down_merged: bool = True
    filter_summary_rows: bool = True
    filter_empty_rows: bool = True
    auto_convert_numbers: bool = True


class SaveDatasetRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    source_file_name: str | None = None
    source_sheet: str | None = None
    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    cleaning_log: list[dict[str, Any]] | None = None


@router.get("/samples", summary="获取系统内置的典型课设测试样本列表")
async def list_sample_files(
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    items = []
    if SAMPLES_DIR.exists():
        for file in sorted(SAMPLES_DIR.iterdir()):
            if file.name in SAMPLE_META:
                meta = SAMPLE_META[file.name]
                items.append({
                    "filename": file.name,
                    "title": meta["title"],
                    "badge": meta["badge"],
                    "description": meta["description"],
                    "size_bytes": file.stat().st_size,
                })
    return {"ok": True, "samples": items}


@router.post("/preview-sample", summary="一键预览系统内置样本")
async def preview_sample_file(
    req: SamplePreviewRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    if req.filename not in SAMPLE_META:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到指定的样本文件「{req.filename}」",
        )

    target_path = SAMPLES_DIR / req.filename
    if not target_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="样本文件物理路径不存在",
        )

    content = target_path.read_bytes()
    try:
        parsed_result = parse_dataset_file(
            file_bytes=content,
            filename=req.filename,
            sheet_name=req.sheet_name,
            preview_limit=20,
        )
    except DataParseError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e

    return {
        "ok": True,
        "filename": req.filename,
        "file_size": len(content),
        "data": parsed_result,
    }


@router.post("/preview", summary="上传自定义文件并获取解析预览")
async def preview_uploaded_file(
    file: UploadFile = File(..., description="支持 .csv 或 .xlsx 文件"),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    filename = file.filename or "uploaded_file"
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"读取上传文件流失败: {e}",
        ) from e

    try:
        parsed_result = parse_dataset_file(
            file_bytes=content,
            filename=filename,
            preview_limit=20,
        )
    except DataParseError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"解析过程发生未知错误: {e}",
        ) from e

    return {
        "ok": True,
        "filename": filename,
        "file_size": len(content),
        "data": parsed_result,
    }


@router.post("/preview-sheet", summary="针对已上传的多 Sheet Excel 切换工作表预览")
async def preview_excel_sheet(
    file: UploadFile = File(...),
    sheet_name: str = Form(...),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    filename = file.filename or "uploaded_file.xlsx"
    try:
        content = await file.read()
        parsed_result = parse_dataset_file(
            file_bytes=content,
            filename=filename,
            sheet_name=sheet_name,
            preview_limit=20,
        )
    except DataParseError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e

    return {
        "ok": True,
        "filename": filename,
        "file_size": len(content),
        "data": parsed_result,
    }


@router.post("/clean-preview", summary="根据清洗规则试算并返回清洗结果与日志")
async def clean_preview(
    req: CleanPreviewRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    """试算清洗结果（不入库），用于在前端展示清洗前后对比。"""
    # 丢掉第一行表头自身，如果传入了 raw_matrix
    matrix_rows = req.raw_matrix[1:] if len(req.raw_matrix) > 1 else req.raw_matrix

    cleaner = DataCleaner(
        headers=req.headers,
        matrix=matrix_rows,
        fill_down_merged=req.fill_down_merged,
        filter_summary_rows=req.filter_summary_rows,
        filter_empty_rows=req.filter_empty_rows,
        auto_convert_numbers=req.auto_convert_numbers,
    )
    cleaned = cleaner.clean()

    return {
        "ok": True,
        "columns": cleaned["columns"],
        "preview_rows": cleaned["rows"][:20],  # 前端表格只展示前 20 行
        "rows": cleaned["rows"],  # 清洗后全量，供前端确认入库（曾经只有 preview 能入库 = 数据丢失）
        "total_rows": cleaned["row_count"],
        "cleaning_logs": cleaned["cleaning_logs"],
        "stats": cleaned["stats"],
    }


@router.post("/save", summary="确认清洗结果并持久化入库")
async def save_dataset(
    req: SaveDatasetRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    """将确认的数据集正式写入 Datasets 表，实现与当前用户的安全隔离。"""
    user_id = user["UserID"]
    
    if not req.rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="数据集内容不能为空，至少应包含 1 行有效数据",
        )

    try:
        new_dataset_id = db_data.create_dataset(
            user_id=user_id,
            name=req.name.strip(),
            columns=req.columns,
            rows=req.rows,
            source_file_name=req.source_file_name,
            source_sheet=req.source_sheet,
            cleaning_log=req.cleaning_log,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"数据入库失败: {e}",
        ) from e

    return {
        "ok": True,
        "dataset_id": new_dataset_id,
        "name": req.name,
        "row_count": len(req.rows),
        "column_count": len(req.columns),
        "message": f"数据集「{req.name}」已成功保存在您的账号名下",
    }


@router.get("/list", summary="获取当前用户已保存的数据集列表")
async def list_user_datasets(
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    """返回当前用户拥有的所有已入库数据集"""
    datasets = db_data.list_datasets(user["UserID"])
    return {
        "ok": True,
        "datasets": datasets,
    }


@router.delete("/{dataset_id}", summary="删除指定数据集")
async def delete_dataset(
    dataset_id: int,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    # 先做引用体检：数据被图表引用时直接删会触发外键报错（500 事故），
    # 必须挡在数据库之前，用人话告诉用户先删图表。
    referencing = db_data.count_charts_using_dataset(user["UserID"], dataset_id)
    if referencing > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"该数据集仍有 {referencing} 张图表在使用，"
                "请先在图表列表中删除相关图表，再删除数据集"
            ),
        )
    affected = db_data.delete_dataset(user["UserID"], dataset_id)
    if affected == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到指定的数据集（或已被删除）",
        )
    return {
        "ok": True,
        "message": "数据集已成功删除",
    }
