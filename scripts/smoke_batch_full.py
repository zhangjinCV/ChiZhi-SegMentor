#!/usr/bin/env python3
"""Full 252-image batch acceptance on the real tank_annotated dataset."""

from __future__ import annotations

import os
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
    if not (TANK / "Annotations").is_dir():
        raise SystemExit("tank_annotated not found")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        settings = RuntimeSettings(
            data_dir=root / "data",
            model_path=CKPT,
            device="cpu",
            token="full-token",
            ready_file=root / "data" / "runtime" / "ready.json",
            web_dist=None,
            dev_mode=True,
            log_file=root / "data" / "logs" / "backend.log",
        )
        settings.ensure_dirs()
        with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
            started = time.perf_counter()
            response = client.post(
                "/api/batch/run",
                json={
                    "annotation_path": str(TANK / "Annotations"),
                    "annotation_format": "voc",
                    "image_root": str(TANK / "JPEGImages"),
                    "threshold": 0.5,
                    "padding": 0,
                    "skip_empty": True,
                },
            )
            assert response.status_code == 200, response.text
            job = response.json()
            job_id = job["id"]
            print("job:", job_id, "images:", job["total_images"], "boxes:", job["total_boxes"])

            deadline = time.time() + 900
            last_print = 0.0
            while time.time() < deadline:
                status = client.get(f"/api/batch/jobs/{job_id}?items=false").json()
                if time.time() - last_print > 10:
                    print(
                        f"  {status['done_images']}/{status['total_images']} images, "
                        f"{status['failed_images']} failed, {status['progress']*100:.1f}%"
                    )
                    last_print = time.time()
                if status["status"] in {"completed", "failed", "cancelled"}:
                    break
                time.sleep(1.0)
            elapsed = time.perf_counter() - started
            print(
                "final:",
                status["status"],
                f"{status['done_images']}/{status['total_images']}",
                f"failed={status['failed_images']}",
                f"elapsed={elapsed:.1f}s",
                f"throughput={status['done_images']/elapsed:.2f} img/s",
            )
            assert status["status"] == "completed", status
            assert status["done_images"] == 252
            assert status["failed_images"] == 0
            full = client.get(f"/api/batch/jobs/{job_id}").json()
            assert len(full["items"]) == 252
            assert all(item["status"] == "done" for item in full["items"])
            assert all(item["results"] for item in full["items"])
            print("FULL 252-IMAGE BATCH PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
