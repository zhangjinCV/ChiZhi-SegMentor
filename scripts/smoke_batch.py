#!/usr/bin/env python3
"""Batch API smoke test: 3 real tank images, VOC input, multi-format export."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from boxmask.api.app import create_app
from boxmask.settings import RuntimeSettings
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]
TANK = Path(os.environ.get("BOXMASK_TANK_DATA", "data/tank_annotated"))
CKPT = REPO / "models" / "boxmask_repvit_best_snapshot.pth"


def main() -> int:
    names = [
        "DJI_20250307152100_0009__000010",
        "DJI_20250307152100_0009__000035",
        "DJI_20250307152100_0009__000044",
    ]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        annotations = root / "annotations"
        images = root / "images"
        annotations.mkdir()
        images.mkdir()
        for name in names:
            shutil.copy2(TANK / "JPEGImages" / f"{name}.jpg", images / f"{name}.jpg")
            shutil.copy2(TANK / "Annotations" / f"{name}.xml", annotations / f"{name}.xml")

        settings = RuntimeSettings(
            data_dir=root / "data",
            model_path=CKPT,
            device="cpu",
            token="batch-token",
            ready_file=root / "data" / "runtime" / "ready.json",
            web_dist=None,
            dev_mode=True,
            log_file=root / "data" / "logs" / "backend.log",
        )
        settings.ensure_dirs()

        with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
            parsed = client.post(
                "/api/batch/parse",
                json={
                    "annotation_path": str(annotations),
                    "annotation_format": "auto",
                    "image_root": str(images),
                    "preview_limit": 10,
                },
            )
            assert parsed.status_code == 200, parsed.text
            preview = parsed.json()
            print("parse:", {k: preview[k] for k in ("format", "image_count", "box_count", "missing_images")})
            assert preview["image_count"] == 3
            assert preview["box_count"] == 3

            started = client.post(
                "/api/batch/run",
                json={
                    "annotation_path": str(annotations),
                    "annotation_format": "auto",
                    "image_root": str(images),
                    "threshold": 0.5,
                    "padding": 0,
                    "skip_empty": True,
                    "stop_on_error": False,
                },
            )
            assert started.status_code == 200, started.text
            job = started.json()
            job_id = job["id"]
            deadline = time.time() + 180
            while job["status"] in {"pending", "running", "paused"} and time.time() < deadline:
                time.sleep(0.4)
                status_response = client.get(f"/api/batch/jobs/{job_id}?items=false")
                assert status_response.status_code == 200, status_response.text
                job = status_response.json()
            print("job:", {k: job[k] for k in ("status", "total_images", "done_images", "failed_images", "done_boxes")})
            assert job["status"] == "completed", job
            assert job["done_images"] == 3
            assert job["failed_images"] == 0
            assert job["done_boxes"] == 3

            full = client.get(f"/api/batch/jobs/{job_id}").json()
            assert len(full["items"]) == 3
            for item in full["items"]:
                assert item["status"] == "done", item
                assert item["results"], item
                result = item["results"][0]
                assert Path(result["mask_path"]).is_file()
                assert Path(result["overlay_path"]).is_file()
                image_response = client.get(result["overlay_url"])
                assert image_response.status_code == 200
                assert image_response.headers["content-type"].startswith("image/")

            export_dir = root / "exports"
            exported = client.post(
                f"/api/batch/jobs/{job_id}/export",
                json={
                    "dest_dir": str(export_dir),
                    "formats": ["mask", "coco", "labelme", "csv"],
                    "naming": "{image}_{box}_{label}",
                },
            )
            assert exported.status_code == 200, exported.text
            export_info = exported.json()
            print("export:", json.dumps(export_info, ensure_ascii=False))
            assert export_info["counts"]["mask"] == 3
            assert (export_dir / "instances.json").is_file()
            assert (export_dir / "results.csv").is_file()
            coco = json.loads((export_dir / "instances.json").read_text(encoding="utf-8"))
            assert len(coco["images"]) == 3
            assert len(coco["annotations"]) == 3
            assert len(list((export_dir / "labelme").glob("*.json"))) == 3
            assert len(list((export_dir / "masks").glob("*.png"))) == 3

    print("BATCH SMOKE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
