from __future__ import annotations

import xml.etree.ElementTree as ET
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


def _text(node: ET.Element | None, key: str, default: str = "") -> str:
    if node is None:
        return default
    value = node.findtext(key)
    return value.strip() if value else default


def scan_voc(annotation_path: Path, image_root: Path | None = None) -> ParseResult:
    xml_files = (
        [annotation_path]
        if annotation_path.is_file() and annotation_path.suffix.lower() == ".xml"
        else sorted(annotation_path.rglob("*.xml"))
    )
    if not xml_files:
        raise ValueError(f"没有找到 VOC XML：{annotation_path}")

    index_roots = ([image_root] if image_root else []) + (
        [annotation_path] if annotation_path.is_dir() else []
    )
    index = build_image_index(index_roots)
    records: list[ImageRecord] = []
    warnings: list[str] = []
    seen: set[str] = set()

    for xml_path in xml_files:
        try:
            root = ET.parse(xml_path).getroot()
        except Exception as exc:
            warnings.append(f"{xml_path.name}: XML 解析失败（{exc}）")
            continue

        filename = _text(root, "filename")
        size = root.find("size")
        width = int(float(_text(size, "width", "0") or 0)) or None
        height = int(float(_text(size, "height", "0") or 0)) or None
        bases = common_image_bases(xml_path, image_root)
        bases.extend([xml_path.parent / "RGB", xml_path.parent.parent / "RGB"])
        record_warnings: list[str] = []
        image_path = resolve_image(filename, bases, index, record_warnings)
        if image_path and (not width or not height):
            width, height = image_size(image_path)
        if not image_path:
            record_warnings.append(f"找不到图片：{filename or xml_path.stem}")

        boxes: list[BoxRecord] = []
        for obj in root.findall("object"):
            bnd = obj.find("bndbox")
            if bnd is None:
                continue
            try:
                x1 = float(_text(bnd, "xmin"))
                y1 = float(_text(bnd, "ymin"))
                x2 = float(_text(bnd, "xmax")) + 1.0  # VOC max is inclusive
                y2 = float(_text(bnd, "ymax")) + 1.0
            except (TypeError, ValueError):
                record_warnings.append("存在无效 bndbox，已跳过")
                continue
            box = BoxRecord(
                x1,
                y1,
                x2,
                y2,
                label=_text(obj, "name", "object") or "object",
                difficult=_text(obj, "difficult", "0") == "1",
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
                name=image_path.name if image_path else (filename or xml_path.stem),
                width=width,
                height=height,
                boxes=boxes,
                source=str(xml_path),
                warnings=record_warnings,
            )
        )

    # Include images that have no XML at all, so the pairing preview can show them.
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
                    warnings=["无标注文件"],
                )
            )

    return ParseResult(format="voc", records=records, warnings=warnings)
