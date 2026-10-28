from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from boxmask.annotations import detect_format, parse_annotations, scan_csv, scan_voc, scan_yolo
from PIL import Image

TANK = Path(os.environ.get("BOXMASK_TANK_DATA", "data/tank_annotated"))
SELECTED = Path(os.environ.get("BOXMASK_TANK_SELECTED", "data/annotation_tank_selected"))


def _image(path: Path, size=(100, 80)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (20, 30, 40)).save(path)


def test_voc_tank_dataset() -> None:
    if not TANK.is_dir():
        pytest.skip("tank dataset not present")
    result = scan_voc(TANK / "Annotations", image_root=TANK / "JPEGImages")
    assert result.format == "voc"
    assert result.image_count == 252
    assert result.box_count == 252
    assert result.missing_images == 0
    record = result.records[0]
    assert record.image_path and Path(record.image_path).is_file()
    assert record.boxes[0].label == "tank"
    assert record.boxes[0].x2 > record.boxes[0].x1


def test_voc_negative_samples() -> None:
    if not SELECTED.is_dir():
        pytest.skip("selected dataset not present")
    result = scan_voc(SELECTED)
    assert result.image_count >= 600
    assert result.box_count >= 200
    assert result.empty_images >= 300
    assert result.missing_images == 0


def test_csv_manifest() -> None:
    if not (TANK / "manifest.csv").is_file():
        pytest.skip("manifest not present")
    result = scan_csv(TANK / "manifest.csv", image_root=TANK / "JPEGImages")
    assert result.image_count == 252
    assert result.box_count == 252
    assert result.records[0].boxes[0].label == "tank"


def test_yolo_labels() -> None:
    if not (TANK / "labels").is_dir():
        pytest.skip("YOLO labels not present")
    result = scan_yolo(TANK / "labels", image_root=TANK / "JPEGImages")
    assert result.image_count == 252
    assert result.box_count == 252
    assert result.records[0].boxes[0].label == "tank"


def test_coco_adapter(tmp_path: Path) -> None:
    _image(tmp_path / "img.png")
    payload = {
        "images": [{"id": 1, "file_name": "img.png", "width": 100, "height": 80}],
        "annotations": [{"id": 1, "image_id": 1, "category_id": 3, "bbox": [10, 20, 30, 40]}],
        "categories": [{"id": 3, "name": "cat"}],
    }
    path = tmp_path / "instances.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert detect_format(path) == "coco"
    result = parse_annotations(path, "auto", tmp_path)
    assert result.image_count == 1
    box = result.records[0].boxes[0]
    assert (box.x1, box.y1, box.x2, box.y2) == (10, 20, 40, 60)
    assert box.label == "cat"


def test_labelme_adapter(tmp_path: Path) -> None:
    _image(tmp_path / "img.png")
    payload = {
        "version": "5.0",
        "imagePath": "img.png",
        "imageWidth": 100,
        "imageHeight": 80,
        "shapes": [
            {"label": "dog", "shape_type": "rectangle", "points": [[5, 6], [45, 56]]}
        ],
    }
    path = tmp_path / "img.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert detect_format(path) == "labelme"
    result = parse_annotations(path, "auto", tmp_path)
    box = result.records[0].boxes[0]
    assert (box.x1, box.y1, box.x2, box.y2) == (5, 6, 45, 56)
    assert box.label == "dog"


def test_generic_json_rows(tmp_path: Path) -> None:
    _image(tmp_path / "img.png")
    payload = [
        {"filename": "img.png", "x1": 1, "y1": 2, "x2": 30, "y2": 40, "label": "x"}
    ]
    path = tmp_path / "rows.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert detect_format(path) == "json"
    result = parse_annotations(path, "auto", tmp_path)
    assert result.records[0].boxes[0].label == "x"


def test_missing_image_is_reported(tmp_path: Path) -> None:
    payload = {
        "images": [{"id": 1, "file_name": "nope.jpg", "width": 100, "height": 80}],
        "annotations": [],
        "categories": [],
    }
    path = tmp_path / "coco.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = parse_annotations(path, "coco")
    assert result.missing_images == 1
    assert not result.records[0].image_path


def test_empty_voc_negative(tmp_path: Path) -> None:
    path = tmp_path / "empty.xml"
    path.write_text(
        """<annotation><filename>img.png</filename><size><width>100</width><height>80</height></size></annotation>""",
        encoding="utf-8",
    )
    result = parse_annotations(path, "voc")
    assert result.records[0].boxes == []
    assert result.missing_images == 1
