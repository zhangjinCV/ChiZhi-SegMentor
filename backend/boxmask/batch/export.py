from __future__ import annotations

import csv
import json
import re
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ..inference.mask_utils import mask_contours
from .models import BatchJob

VALID_FORMATS = {"mask", "overlay", "coco", "labelme", "csv"}


def _safe(value: str, fallback: str = "item") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" .")
    return cleaned or fallback


def _unique_path(directory: Path, name: str) -> Path:
    candidate = directory / name
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    index = 2
    while True:
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _name_from_template(template: str, item, result, box_number: int) -> str:
    values = {
        "image": _safe(Path(item.name).stem),
        "index": f"{item.index:05d}",
        "box": str(box_number),
        "label": _safe(result.label),
    }
    name = template or "{image}_{box}_{label}"
    for key, value in values.items():
        name = name.replace("{" + key + "}", value)
    return _safe(name, "mask")


def _read_mask(path: str) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L")) > 0


def _mask_polygons(path: str) -> list[list[float]]:
    contours = mask_contours(_read_mask(path))
    polygons: list[list[float]] = []
    for contour in contours:
        if len(contour) < 3:
            continue
        flat: list[float] = []
        for x, y in contour:
            flat.extend([round(float(x), 2), round(float(y), 2)])
        if len(flat) >= 6:
            polygons.append(flat)
    return polygons


def export_job(
    job: BatchJob,
    dest_dir: str | None,
    formats: list[str] | None,
    naming: str | None,
) -> dict[str, Any]:
    selected = [fmt for fmt in (formats or ["mask"]) if fmt in VALID_FORMATS]
    if not selected:
        raise ValueError(f"不支持的导出格式：{formats}")
    done_items = [item for item in job.items if item.results]
    if not done_items:
        raise ValueError("任务还没有可导出的结果")

    dest = Path(dest_dir).expanduser() if dest_dir else Path(job.output_dir) / "export"
    dest.mkdir(parents=True, exist_ok=True)
    if not dest.is_dir():
        raise ValueError(f"导出路径不是文件夹：{dest}")

    counts = {"images": 0, "boxes": 0, "mask": 0, "overlay": 0}
    mask_dir = dest / "masks"
    overlay_dir = dest / "overlays"
    if "mask" in selected:
        mask_dir.mkdir(parents=True, exist_ok=True)
    if "overlay" in selected:
        overlay_dir.mkdir(parents=True, exist_ok=True)

    coco_images: list[dict[str, Any]] = []
    coco_annotations: list[dict[str, Any]] = []
    category_ids: dict[str, int] = {}
    labelme_files: list[Path] = []
    csv_rows: list[dict[str, Any]] = []
    annotation_id = 1

    for item in done_items:
        counts["images"] += 1
        if not item.results:
            continue
        item_polygons: list[dict[str, Any]] = []
        for result in item.results:
            counts["boxes"] += 1
            box_number = result.box_index + 1
            base_name = _name_from_template(naming or "{image}_{box}_{label}", item, result, box_number)

            if "mask" in selected:
                target = _unique_path(mask_dir, f"{base_name}.png")
                shutil.copy2(result.mask_path, target)
                counts["mask"] += 1
            if "overlay" in selected:
                target = _unique_path(overlay_dir, f"{base_name}_overlay.png")
                shutil.copy2(result.overlay_path, target)
                counts["overlay"] += 1

            polygons = _mask_polygons(result.mask_path)
            label = result.label or "object"
            category_id = category_ids.setdefault(label, len(category_ids) + 1)

            if "coco" in selected and polygons:
                x1, y1, x2, y2 = result.box_used if len(result.box_used) == 4 else (
                    result.box[0],
                    result.box[1],
                    result.box[2],
                    result.box[3],
                )
                coco_annotations.append(
                    {
                        "id": annotation_id,
                        "image_id": item.index,
                        "category_id": category_id,
                        "bbox": [
                            round(float(x1), 2),
                            round(float(y1), 2),
                            round(max(0.0, float(x2) - float(x1)), 2),
                            round(max(0.0, float(y2) - float(y1)), 2),
                        ],
                        "area": int(result.area_px),
                        "segmentation": polygons,
                        "iscrowd": 0,
                    }
                )
                annotation_id += 1

            if "labelme" in selected:
                for polygon in polygons:
                    points = [[polygon[i], polygon[i + 1]] for i in range(0, len(polygon), 2)]
                    item_polygons.append(
                        {
                            "label": label,
                            "points": points,
                            "group_id": None,
                            "shape_type": "polygon",
                            "flags": {},
                        }
                    )

            if "csv" in selected:
                csv_rows.append(
                    {
                        "image": item.name,
                        "image_path": item.image_path or "",
                        "box_index": result.box_index,
                        "label": label,
                        "x1": round(float(result.box[0]), 2),
                        "y1": round(float(result.box[1]), 2),
                        "x2": round(float(result.box[2]), 2),
                        "y2": round(float(result.box[3]), 2),
                        "box_used": " ".join(str(v) for v in result.box_used),
                        "area_px": result.area_px,
                        "area_ratio": round(result.area_ratio, 6),
                        "mean_prob": result.mean_prob,
                        "latency_ms": round(result.latency_ms, 2),
                        "mask_path": result.mask_path,
                        "warning": result.warning or "",
                    }
                )

        if "coco" in selected:
            width = item.width
            height = item.height
            if not width or not height:
                with Image.open(item.results[0].mask_path) as mask_image:
                    width, height = mask_image.size
            coco_images.append(
                {
                    "id": item.index,
                    "file_name": item.name,
                    "width": int(width or 0),
                    "height": int(height or 0),
                }
            )

        if "labelme" in selected and item_polygons:
            width = item.width
            height = item.height
            if not width or not height:
                with Image.open(item.results[0].mask_path) as mask_image:
                    width, height = mask_image.size
            labelme_dir = dest / "labelme"
            labelme_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": "5.0",
                "flags": {},
                "shapes": item_polygons,
                "imagePath": item.name,
                "imageData": None,
                "imageHeight": int(height or 0),
                "imageWidth": int(width or 0),
            }
            path = labelme_dir / f"{_safe(Path(item.name).stem)}.json"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            labelme_files.append(path)

    if "coco" in selected:
        images = {image["id"]: image for image in coco_images}
        categories = [
            {"id": category_id, "name": name, "supercategory": "object"}
            for name, category_id in sorted(category_ids.items(), key=lambda item: item[1])
        ]
        payload = {
            "info": {
                "description": f"Chizhi SegMentor batch export {job.id}",
                "version": "1.0",
            },
            "licenses": [],
            "images": list(images.values()),
            "annotations": coco_annotations,
            "categories": categories,
        }
        (dest / "instances.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if "csv" in selected:
        fields = [
            "image",
            "image_path",
            "box_index",
            "label",
            "x1",
            "y1",
            "x2",
            "y2",
            "box_used",
            "area_px",
            "area_ratio",
            "mean_prob",
            "latency_ms",
            "mask_path",
            "warning",
        ]
        with (dest / "results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(csv_rows)

    return {
        "dest_dir": str(dest),
        "formats": selected,
        "counts": counts,
        "coco": str(dest / "instances.json") if "coco" in selected else None,
        "csv": str(dest / "results.csv") if "csv" in selected else None,
        "labelme_files": len(labelme_files),
    }
