#!/usr/bin/env python3
"""Smoke-test the PyInstaller sidecar (windowed, ready.json, real inference)."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXE = REPO / "backend" / "dist" / "boxmask-backend" / "boxmask-backend.exe"
MODEL = REPO / "models" / "boxmask_repvit_best_snapshot.pth"
IMAGE = Path(os.environ.get("BOXMASK_SMOKE_IMAGE", "data/tank_annotated/JPEGImages/DJI_20250307152100_0009__000010.jpg"))


def main() -> int:
    if not EXE.is_file():
        raise SystemExit(f"sidecar not built: {EXE}")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ready_file = root / "runtime" / "ready.json"
        env = {
            **os.environ,
            "BOXMASK_DATA_DIR": str(root / "data"),
            "BOXMASK_READY_FILE": str(ready_file),
            "BOXMASK_LOG_FILE": str(root / "logs" / "backend.log"),
            "BOXMASK_MODEL": str(MODEL),
            "BOXMASK_DEV": "1",
        }
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(
            [str(EXE), "--port", "0"],
            cwd=str(EXE.parent),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        try:
            deadline = time.time() + 180
            info = None
            while time.time() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"sidecar exited early: {process.returncode}")
                if ready_file.is_file():
                    try:
                        info = json.loads(ready_file.read_text(encoding="utf-8"))
                        if info.get("port"):
                            break
                    except Exception:
                        pass
                time.sleep(0.2)
            if not info:
                raise RuntimeError("sidecar did not become ready")
            base = f"http://127.0.0.1:{info['port']}"
            with urllib.request.urlopen(f"{base}/api/health", timeout=30) as response:
                health = json.loads(response.read())
            print("health:", json.dumps(
                {"loaded": health["model"]["loaded"], "device": health["model"]["device"]},
                ensure_ascii=False,
            ))
            assert health["model"]["loaded"] is True, health
            token = info["token"]
            body = json.dumps(
                {
                    "image_path": str(IMAGE),
                    "boxes": [{"x1": 503, "y1": 1, "x2": 1676, "y2": 604}],
                    "threshold": 0.5,
                }
            ).encode()
            request = urllib.request.Request(
                f"{base}/api/segment",
                data=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                result = json.loads(response.read())
            item = result["results"][0]
            print("segment:", json.dumps(
                {"area_px": item["area_px"], "latency_ms": round(item["latency_ms"], 1)},
                ensure_ascii=False,
            ))
            assert item["area_px"] > 0
        finally:
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
    print("PACKAGED SIDECAR SMOKE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
