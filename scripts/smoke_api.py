#!/usr/bin/env python3
"""End-to-end smoke test with the real checkpoint (CPU).

Starts the FastAPI app in-process via TestClient, segments one real tank
image, and writes the mask/overlay previews to backend/tests/fixtures/.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from boxmask.api.app import create_app
from boxmask.settings import RuntimeSettings
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]
IMAGE = Path(os.environ.get("BOXMASK_SMOKE_IMAGE", "data/tank_annotated/JPEGImages/DJI_20250307152100_0009__000010.jpg"))
XML = Path(os.environ.get("BOXMASK_SMOKE_XML", "data/tank_annotated/Annotations/DJI_20250307152100_0009__000010.xml"))
CKPT = REPO / "models" / "boxmask_repvit_best_snapshot.pth"
OUT = REPO / "backend" / "tests" / "fixtures"


def read_box() -> list[float]:
    root = ET.parse(XML).getroot()
    bnd = root.find("object/bndbox")
    assert bnd is not None
    xmin = float(bnd.findtext("xmin"))
    ymin = float(bnd.findtext("ymin"))
    xmax = float(bnd.findtext("xmax"))
    ymax = float(bnd.findtext("ymax"))
    return [xmin, ymin, xmax + 1.0, ymax + 1.0]


def main() -> int:
    assert IMAGE.is_file(), IMAGE
    assert XML.is_file(), XML
    assert CKPT.is_file(), CKPT
    OUT.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        settings = RuntimeSettings(
            data_dir=Path(tmp) / "data",
            model_path=CKPT,
            device="cpu",
            token="smoke-token",
            ready_file=Path(tmp) / "data" / "runtime" / "ready.json",
            web_dist=None,
            dev_mode=True,
            log_file=Path(tmp) / "data" / "logs" / "backend.log",
        )
        settings.ensure_dirs()
        with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
            health = client.get("/api/health").json()
            print("health:", json.dumps(
                {
                    "loaded": health["model"]["loaded"],
                    "device": health["model"]["device"],
                    "sha256": (health["model"]["model_hash"] or "")[:12],
                },
                ensure_ascii=False,
            ))
            box = read_box()
            started = time.perf_counter()
            response = client.post(
                "/api/segment",
                json={
                    "image_path": str(IMAGE),
                    "boxes": [{"x1": box[0], "y1": box[1], "x2": box[2], "y2": box[3]}],
                    "threshold": 0.5,
                    "padding": 0,
                },
            )
            elapsed = (time.perf_counter() - started) * 1000
            assert response.status_code == 200, response.text
            body = response.json()
            item = body["results"][0]
            print(
                "segment:",
                json.dumps(
                    {
                        "width": body["width"],
                        "height": body["height"],
                        "area_px": item["area_px"],
                        "area_ratio": round(item["area_ratio"], 5),
                        "mean_prob": round(item["mean_prob"], 4) if item["mean_prob"] else None,
                        "latency_ms": round(item["latency_ms"], 1),
                        "total_ms": round(elapsed, 1),
                    },
                    ensure_ascii=False,
                ),
            )
            assert item["area_px"] > 0, "model returned an empty mask"
            (OUT / "smoke_mask.png").write_bytes(base64.b64decode(item["mask_png_base64"]))
            (OUT / "smoke_overlay.png").write_bytes(
                base64.b64decode(item["overlay_png_base64"])
            )

            preview = client.get(
                "/api/model/input-preview",
                params={
                    "image_path": str(IMAGE),
                    "x1": box[0],
                    "y1": box[1],
                    "x2": box[2],
                    "y2": box[3],
                },
            )
            assert preview.status_code == 200, preview.text
            (OUT / "smoke_branch_full.png").write_bytes(
                base64.b64decode(preview.json()["full_png_base64"])
            )
            (OUT / "smoke_branch_crop.png").write_bytes(
                base64.b64decode(preview.json()["crop_png_base64"])
            )

            signed = client.get("/api/file/sign", params={"path": str(IMAGE)})
            assert signed.status_code == 200, signed.text
            url = signed.json()["url"]
            image_response = client.get(url)
            assert image_response.status_code == 200
            assert image_response.headers["content-type"].startswith("image/")

    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
