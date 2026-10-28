from __future__ import annotations

import json
from pathlib import Path

from .base import BoxRecord, ImageRecord, ParseResult
from .coco import scan_coco
from .csv_json import scan_csv, scan_json_rows
from .labelme import scan_labelme
from .voc import scan_voc
from .yolo import scan_yolo

FORMATS = ("auto", "voc", "coco", "labelme", "yolo", "csv", "json")


def _inspect_json(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(data, dict):
        if "images" in data and "annotations" in data:
            return "coco"
        if "shapes" in data:
            return "labelme"
        if any(isinstance(data.get(key), list) for key in ("records", "items", "annotations", "data")):
            return "json"
    if isinstance(data, list):
        return "json"
    return None


def detect_format(path: Path) -> str:
    if path.is_file():
        suffix = path.suffix.lower()
        if suffix == ".xml":
            return "voc"
        if suffix == ".json":
            return _inspect_json(path) or "json"
        if suffix == ".csv":
            return "csv"
        if suffix in {".txt", ".yaml", ".yml"}:
            return "yolo"
        raise ValueError(f"无法识别的标注文件：{path.name}")

    json_formats: list[str] = []
    if any(path.rglob("*.xml")):
        return "voc"
    for json_path in sorted(path.rglob("*.json")):
        fmt = _inspect_json(json_path)
        if fmt == "coco":
            return "coco"
        if fmt:
            json_formats.append(fmt)
    if json_formats:
        return json_formats[0]
    if any(candidate.suffix.lower() == ".csv" for candidate in path.rglob("*")):
        return "csv"
    if any(candidate.suffix.lower() == ".txt" and candidate.name.lower() != "classes.txt" for candidate in path.rglob("*")):
        return "yolo"
    raise ValueError(f"无法自动识别标注格式：{path}")


def parse_annotations(
    annotation_path: str | Path,
    annotation_format: str = "auto",
    image_root: str | Path | None = None,
) -> ParseResult:
    path = Path(annotation_path).expanduser()
    root = Path(image_root).expanduser() if image_root else None
    if not path.exists():
        raise FileNotFoundError(f"标注路径不存在：{path}")
    if root is not None and not root.exists():
        raise FileNotFoundError(f"图片路径不存在：{root}")

    requested = (annotation_format or "auto").lower()
    if requested not in FORMATS:
        raise ValueError(f"不支持的标注格式：{annotation_format}")
    fmt = detect_format(path) if requested == "auto" else requested

    if fmt == "voc":
        return scan_voc(path, root)
    if fmt == "coco":
        return scan_coco(path, root)
    if fmt == "labelme":
        return scan_labelme(path, root)
    if fmt == "yolo":
        return scan_yolo(path, root)
    if fmt == "csv":
        return scan_csv(path, root)
    if fmt == "json":
        if path.is_dir():
            candidates = sorted(path.rglob("*.json"))
            if not candidates:
                raise ValueError(f"没有找到 JSON：{path}")
            return scan_json_rows(candidates[0], root)
        return scan_json_rows(path, root)
    raise ValueError(f"不支持的标注格式：{fmt}")


__all__ = [
    "BoxRecord",
    "ImageRecord",
    "ParseResult",
    "FORMATS",
    "detect_format",
    "parse_annotations",
    "scan_coco",
    "scan_csv",
    "scan_json_rows",
    "scan_labelme",
    "scan_voc",
    "scan_yolo",
]
