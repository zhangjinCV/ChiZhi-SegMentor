from __future__ import annotations

import json
from pathlib import Path

from .base import (
    BoxRecord,
    ImageRecord,
    ParseResult,
    build_image_index,
    common_image_bases,
    image_size,
    iter_images,
    resolve_image,
)


def _shape_bbox(points: list[list[float]]) -> tuple[float, float, float, float] | None:
    if not points:
        return None
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def scan_labelme(annotation_path: Path, image_root: Path | None = None) -> ParseResult:
    json_files = (
        [annotation_path]
        if annotation_path.is_file() and annotation_path.suffix.lower() == ".json"
        else sorted(annotation_path.rglob("*.json"))
    )
    if not json_files:
        raise ValueError(f"没有找到 LabelMe JSON：{annotation_path}")

    index = build_image_index([image_root] if image_root else [])
    records: list[ImageRecord] = []
    warnings: list[str] = []
    seen: set[str] = set()

    for json_path in json_files:
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            warnings.append(f"{json_path.name}: JSON 解析失败（{exc}）")
            continue
        if not isinstance(data, dict) or "shapes" not in data:
            continue

        image_name = str(data.get("imagePath") or json_path.with_suffix(".jpg").name)
        width = int(data.get("imageWidth") or 0) or None
        height = int(data.get("imageHeight") or 0) or None
        bases = common_image_bases(json_path, image_root)
        record_warnings: list[str] = []
        image_path = resolve_image(image_name, bases, index, record_warnings)
        if image_path and (not width or not height):
            width, height = image_size(image_path)
        if not image_path:
            record_warnings.append(f"找不到图片：{image_name}")

        boxes: list[BoxRecord] = []
        for shape in data.get("shapes", []):
            bbox = _shape_bbox(shape.get("points") or [])
            if bbox is None:
                continue
            box = BoxRecord(
                *bbox,
                label=str(shape.get("label") or "object"),
            ).normalized(width, height)
            if box is None:
                record_warnings.append("存在零面积 shape，已跳过")
                continue
            boxes.append(box)

        if image_path:
            seen.add(str(image_path.resolve()).lower())
        records.append(
            ImageRecord(
                image_path=str(image_path) if image_path else None,
                name=image_path.name if image_path else Path(image_name).name,
                width=width,
                height=height,
                boxes=boxes,
                source=str(json_path),
                warnings=record_warnings,
            )
        )

    if image_root and image_root.is_dir():
        for image_path in iter_images(image_root):
            if str(image_path.resolve()).lower() in seen:
                continue
            width, height = image_size(image_path)
            records.append(
                ImageRecord(
                    image_path=str(image_path),
                    name=image_path.name,
                    width=width,
                    height=height,
                    boxes=[],
                    source="",
                    warnings=["无 LabelMe 标注"],
                )
            )

    return ParseResult(format="labelme", records=records, warnings=warnings)
