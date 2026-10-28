from __future__ import annotations

from pathlib import Path

import yaml

from .base import (
    BoxRecord,
    ImageRecord,
    ParseResult,
    image_size,
    iter_images,
)


def _load_classes(annotation_path: Path) -> dict[int, str]:
    candidates: list[Path] = []
    if annotation_path.is_file() and annotation_path.suffix.lower() in {".yaml", ".yml"}:
        candidates.append(annotation_path)
    candidates.extend(
        [
            annotation_path / "classes.txt" if annotation_path.is_dir() else annotation_path.parent / "classes.txt",
            annotation_path.parent / "classes.txt",
            annotation_path.parent / "data.yaml",
            annotation_path.parent.parent / "classes.txt",
            annotation_path.parent.parent / "data.yaml",
        ]
    )
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            if candidate.suffix.lower() in {".yaml", ".yml"}:
                data = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
                names = data.get("names") or {}
                if isinstance(names, dict):
                    return {int(key): str(value) for key, value in names.items()}
                if isinstance(names, list):
                    return {index: str(value) for index, value in enumerate(names)}
            else:
                lines = [line.strip() for line in candidate.read_text(encoding="utf-8").splitlines()]
                return {index: name or f"class_{index}" for index, name in enumerate(lines) if name}
        except Exception:
            continue
    return {}


def scan_yolo(annotation_path: Path, image_root: Path | None = None) -> ParseResult:
    if annotation_path.is_file() and annotation_path.suffix.lower() in {".yaml", ".yml"}:
        labels_dir = annotation_path.parent
    elif annotation_path.is_file():
        labels_dir = annotation_path.parent
    else:
        labels_dir = annotation_path
    label_files = (
        [annotation_path]
        if annotation_path.is_file() and annotation_path.suffix.lower() == ".txt"
        else sorted(labels_dir.rglob("*.txt"))
    )
    label_files = [path for path in label_files if path.name.lower() not in {"classes.txt"}]
    if not label_files:
        raise ValueError(f"没有找到 YOLO txt：{annotation_path}")

    roots: list[Path] = []
    if image_root is not None:
        roots.append(image_root)
    else:
        roots.extend(
            [
                labels_dir.parent / "JPEGImages",
                labels_dir.parent / "images",
                labels_dir.parent,
            ]
        )
    images: list[Path] = []
    for root in roots:
        if root.is_dir():
            images.extend(iter_images(root))
    if not images:
        raise ValueError("YOLO 需要图片目录；请选择图片文件夹")
    by_stem: dict[str, Path] = {}
    duplicate_stems: set[str] = set()
    for image in images:
        key = image.stem.lower()
        if key in by_stem:
            duplicate_stems.add(key)
        else:
            by_stem[key] = image

    classes = _load_classes(annotation_path)
    records: list[ImageRecord] = []
    warnings: list[str] = []
    seen: set[str] = set()

    for label_file in label_files:
        stem = label_file.stem.lower()
        image_path = by_stem.get(stem)
        record_warnings: list[str] = []
        if stem in duplicate_stems:
            record_warnings.append("存在同名图片，已使用其中一个")
        if not image_path:
            record_warnings.append(f"找不到同名图片：{label_file.stem}")
            records.append(
                ImageRecord(
                    image_path=None,
                    name=label_file.stem,
                    boxes=[],
                    source=str(label_file),
                    warnings=record_warnings,
                )
            )
            continue

        width, height = image_size(image_path)
        boxes: list[BoxRecord] = []
        for line_no, line in enumerate(label_file.read_text(encoding="utf-8").splitlines(), 1):
            parts = line.split()
            if not parts:
                continue
            if len(parts) != 5:
                record_warnings.append(f"第 {line_no} 行不是 5 列，已跳过")
                continue
            try:
                class_id = int(float(parts[0]))
                cx, cy, bw, bh = (float(value) for value in parts[1:])
            except ValueError:
                record_warnings.append(f"第 {line_no} 行数值无效，已跳过")
                continue
            if not width or not height:
                record_warnings.append("无法读取图片尺寸，跳过该图所有框")
                boxes = []
                break
            box = BoxRecord(
                (cx - bw / 2) * width,
                (cy - bh / 2) * height,
                (cx + bw / 2) * width,
                (cy + bh / 2) * height,
                label=classes.get(class_id, f"class_{class_id}"),
            ).normalized(width, height)
            if box is None:
                record_warnings.append(f"第 {line_no} 行框面积为 0，已跳过")
                continue
            boxes.append(box)

        seen.add(str(image_path.resolve()).lower())
        records.append(
            ImageRecord(
                image_path=str(image_path),
                name=image_path.name,
                width=width,
                height=height,
                boxes=boxes,
                source=str(label_file),
                warnings=record_warnings,
            )
        )

    for image_path in iter_images(roots[0]) if roots and roots[0].is_dir() else []:
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
                warnings=["无 YOLO 标注"],
            )
        )

    return ParseResult(format="yolo", records=records, warnings=warnings)
