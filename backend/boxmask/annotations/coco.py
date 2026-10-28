from __future__ import annotations

import json
from collections import defaultdict
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


def scan_coco(annotation_path: Path, image_root: Path | None = None) -> ParseResult:
    if annotation_path.is_dir():
        candidates = sorted(annotation_path.rglob("*.json"))
        if not candidates:
            raise ValueError(f"没有找到 COCO JSON：{annotation_path}")
        json_path = candidates[0]
    else:
        json_path = annotation_path

    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "images" not in data or "annotations" not in data:
        raise ValueError(f"不是 COCO 格式：{json_path}")

    categories = {
        int(category["id"]): str(category.get("name", category["id"]))
        for category in data.get("categories", [])
        if "id" in category
    }
    by_image: dict[int, list[dict]] = defaultdict(list)
    for annotation in data.get("annotations", []):
        by_image[int(annotation.get("image_id", -1))].append(annotation)

    index = build_image_index([image_root] if image_root else [])
    bases = common_image_bases(json_path, image_root)
    records: list[ImageRecord] = []
    warnings: list[str] = []
    seen: set[str] = set()

    for image in data.get("images", []):
        file_name = str(image.get("file_name", ""))
        record_warnings: list[str] = []
        image_path = resolve_image(file_name, bases, index, record_warnings)
        width = int(image.get("width") or 0) or None
        height = int(image.get("height") or 0) or None
        if image_path and (not width or not height):
            width, height = image_size(image_path)
        if not image_path:
            record_warnings.append(f"找不到图片：{file_name}")

        boxes: list[BoxRecord] = []
        for annotation in by_image.get(int(image.get("id", -1)), []):
            bbox = annotation.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            x, y, w, h = (float(v) for v in bbox)
            box = BoxRecord(
                x,
                y,
                x + w,
                y + h,
                label=categories.get(int(annotation.get("category_id", -1)), "object"),
                confidence=float(annotation["score"]) if "score" in annotation else None,
                difficult=bool(annotation.get("iscrowd", 0)),
            ).normalized(width, height)
            if box is None:
                record_warnings.append("存在零面积框，已跳过")
                continue
            boxes.append(box)

        if image_path:
            seen.add(str(image_path.resolve()).lower())
        records.append(
            ImageRecord(
                image_path=str(image_path) if image_path else None,
                name=image_path.name if image_path else Path(file_name).name,
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
                    source=str(json_path),
                    warnings=["无 COCO 标注"],
                )
            )

    return ParseResult(format="coco", records=records, warnings=warnings)
