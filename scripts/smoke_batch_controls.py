#!/usr/bin/env python3
"""Verify batch pause/resume, cancel, and retry-failed controls."""

from __future__ import annotations

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


def poll(client: TestClient, job_id: str, timeout: float = 240) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/batch/jobs/{job_id}?items=false").json()
        if data["status"] in {"completed", "failed", "cancelled"}:
            return data
        time.sleep(0.2)
    raise TimeoutError(job_id)


def wait_idle(client: TestClient, timeout: float = 60) -> None:
    manager = client.app.state.boxmask.batch
    deadline = time.time() + timeout
    while time.time() < deadline:
        thread = manager._thread
        if thread is None or not thread.is_alive():
            return
        time.sleep(0.1)
    raise TimeoutError("batch worker did not stop")


def main() -> int:
    names = sorted(path.stem for path in (TANK / "Annotations").glob("*.xml"))[:20]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        images = root / "images"
        annotations = root / "annotations"
        images.mkdir()
        annotations.mkdir()
        for name in names:
            shutil.copy2(TANK / "JPEGImages" / f"{name}.jpg", images / f"{name}.jpg")
            shutil.copy2(TANK / "Annotations" / f"{name}.xml", annotations / f"{name}.xml")

        settings = RuntimeSettings(
            data_dir=root / "data",
            model_path=CKPT,
            device="cpu",
            token="controls-token",
            ready_file=root / "data" / "runtime" / "ready.json",
            web_dist=None,
            dev_mode=True,
            log_file=root / "data" / "logs" / "backend.log",
        )
        settings.ensure_dirs()
        with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
            payload = {
                "annotation_path": str(annotations),
                "annotation_format": "voc",
                "image_root": str(images),
                "threshold": 0.5,
                "padding": 0,
                "skip_empty": True,
            }
            job = client.post("/api/batch/run", json=payload).json()
            job_id = job["id"]
            paused = client.post(f"/api/batch/jobs/{job_id}/pause").json()
            assert paused["status"] == "paused", paused
            time.sleep(1.0)
            middle = client.get(f"/api/batch/jobs/{job_id}?items=false").json()
            print("paused at:", middle["done_images"], "/", middle["total_images"])
            resumed = client.post(f"/api/batch/jobs/{job_id}/resume").json()
            assert resumed["status"] == "running", resumed
            final = poll(client, job_id)
            wait_idle(client)
            print("resumed final:", final["status"], final["done_images"], "/", final["total_images"])
            assert final["status"] == "completed"
            assert final["done_images"] == len(names)

            cancelled_job = client.post("/api/batch/run", json=payload).json()
            cancelled_id = cancelled_job["id"]
            client.post(f"/api/batch/jobs/{cancelled_id}/pause")
            cancelled = client.post(f"/api/batch/jobs/{cancelled_id}/cancel").json()
            assert cancelled["status"] == "cancelled", cancelled
            time.sleep(0.8)
            wait_idle(client)
            after = client.get(f"/api/batch/jobs/{cancelled_id}?items=false").json()
            print("cancelled:", after["status"], after["done_images"], "/", after["total_images"])
            assert after["status"] == "cancelled"

            # One valid image + one XML pointing at a missing image.
            bad_root = root / "bad"
            bad_ann = bad_root / "annotations"
            bad_img = bad_root / "images"
            bad_ann.mkdir(parents=True)
            bad_img.mkdir()
            name = names[0]
            shutil.copy2(TANK / "JPEGImages" / f"{name}.jpg", bad_img / f"{name}.jpg")
            shutil.copy2(TANK / "Annotations" / f"{name}.xml", bad_ann / f"{name}.xml")
            missing_xml = bad_ann / "missing.xml"
            missing_xml.write_text(
                """<annotation><filename>missing.jpg</filename>
                <size><width>1920</width><height>1080</height></size>
                <object><name>tank</name><bndbox><xmin>10</xmin><ymin>10</ymin>
                <xmax>300</xmax><ymax>300</ymax></bndbox></object></annotation>""",
                encoding="utf-8",
            )
            bad_payload = {
                "annotation_path": str(bad_ann),
                "annotation_format": "voc",
                "image_root": str(bad_img),
                "threshold": 0.5,
                "skip_empty": False,
            }
            bad_job = client.post("/api/batch/run", json=bad_payload).json()
            bad_id = bad_job["id"]
            bad_final = poll(client, bad_id)
            print("bad final:", bad_final["status"], bad_final["done_images"], bad_final["failed_images"])
            assert bad_final["failed_images"] == 1
            assert bad_final["done_images"] == 1
            retried = client.post(f"/api/batch/jobs/{bad_id}/retry")
            assert retried.status_code == 200, retried.text
            bad_again = poll(client, bad_id)
            wait_idle(client)
            print("retry final:", bad_again["status"], bad_again["failed_images"])
            assert bad_again["failed_images"] == 1
            assert bad_again["done_images"] == 1

    print("BATCH CONTROLS SMOKE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
