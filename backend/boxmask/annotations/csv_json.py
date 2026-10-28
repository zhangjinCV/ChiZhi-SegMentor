from __future__ import annotations

import csv
import json
from collections import OrderedDict
from pathlib import Path

from .base import (
    BoxRecord,
    ImageRecord,
    ParseResult,
    build_image_index,
    common_image_bases,
    image_size,
    resolve_image,
)

_NAME_KEYS = ("image", "filename", "file", "path", "image_path", "name")
_LABEL_KEYS = ("class", "label", "category")
_COORD_SETS = (
    ("xmin_1920", "ymin_1920", "xmax_1920", "ymax_1920"),
    ("x1", "y1", "x2", "y2"),
    ("xmin", "ymin", "xmax", "ymax"),
    ("left", "top", "right", "bottom"),
)


def _pick_first(row: dict, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        if key in row and str(row[key]).strip():
            return key
    return None


def _coord_keys(row: dict) -> tuple[str, str, str, str] | None:
    for keys in _COORD_SETS:
        if all(key in row for key in keys):
            return keys  # type: ignore[return-value]
    return None


def _rows_to_result(rows: list[dict], annotation_path: Path, image_root: Path | None) -> ParseResult:
    if not rows:
        raise ValueError(f"文件为空：{annotation_path}")
    name_key = _pick_first(rows[0], _NAME_KEYS)
    if name_key is None:
        raise ValueError("CSV/JSON 缺少图片名列（image/filename/path 等）")

    image_key = None
    for row in rows:
        image_key = _coord_keys(row)
        if image_key:
            break
    if image_key is None:
        raise ValueError(
            "CSV/JSON 缺少坐标列。支持 x1/y1/x2/y2、xmin/ymin/xmax/ymax、xmin_1920/... 等。"
        )

    label_key = _pick_first(rows[0], _LABEL_KEYS)
    bases = common_image_bases(annotation_path, image_root)
    index = build_image_index([image_root] if image_root else [])
    grouped: OrderedDict[str, list[dict]] = OrderedDict()
    for row in rows:
        name = str(row.get(name_key, "")).strip()
        if not name:
            continue
        grouped.setdefault(name, []).append(row)

    records: list[ImageRecord] = []
    warnings: list[str] = []
    for name, group in grouped.items():
        record_warnings: list[str] = []
        image_path = resolve_image(name, bases, index, record_warnings)
        width = height = None
        if image_path:
            width, height = image_size(image_path)
        else:
            record_warnings.append(f"找不到图片：{name}")

        boxes: list[BoxRecord] = []
        for row in group:
            try:
                x1 = float(row[image_key[0]])
                y1 = float(row[image_key[1]])
                x2 = float(row[image_key[2]])
                y2 = float(row[image_key[3]])
            except (TypeError, ValueError):
                record_warnings.append("存在无效坐标，已跳过")
                continue
            # Common CSV convention: xmax/ymax may be inclusive.
            if image_key[2].startswith("xmax") or image_key[3].startswith("ymax"):
                x2 += 1.0
                y2 += 1.0
            box = BoxRecord(
                x1,
                y1,
                x2,
                y2,
                label=str(row.get(label_key, "object")) if label_key else "object",
            ).normalized(width, height)
            if box is None:
                record_warnings.append("存在零面积框，已跳过")
                continue
            boxes.append(box)

        records.append(
            ImageRecord(
                image_path=str(image_path) if image_path else None,
                name=image_path.name if image_path else Path(name).name,
                width=width,
                height=height,
                boxes=boxes,
                source=str(annotation_path),
                warnings=record_warnings,
            )
        )

    return ParseResult(format="csv", records=records, warnings=warnings)


def scan_csv(annotation_path: Path, image_root: Path | None = None) -> ParseResult:
    with annotation_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return _rows_to_result(rows, annotation_path, image_root)


def scan_json_rows(annotation_path: Path, image_root: Path | None = None) -> ParseResult:
    data = json.loads(annotation_path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for key in ("records", "items", "annotations", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise ValueError(f"不是通用 JSON 行列表：{annotation_path}")
    return _rows_to_result([row for row in data if isinstance(row, dict)], annotation_path, image_root)
