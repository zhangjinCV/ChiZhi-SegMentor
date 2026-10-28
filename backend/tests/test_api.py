from __future__ import annotations

from pathlib import Path

from boxmask.api.app import create_app
from boxmask.settings import RuntimeSettings
from fastapi.testclient import TestClient
from PIL import Image

TOKEN = "test-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def make_client(tmp_path: Path) -> TestClient:
    settings = RuntimeSettings(
        data_dir=tmp_path / "data",
        model_path=tmp_path / "missing.pth",
        token=TOKEN,
        ready_file=tmp_path / "data" / "runtime" / "ready.json",
        web_dist=None,
        dev_mode=False,
        log_file=tmp_path / "data" / "logs" / "backend.log",
    )
    settings.ensure_dirs()
    return TestClient(create_app(settings), base_url="http://127.0.0.1")


def test_health_is_public_and_reports_missing_model(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["model"]["loaded"] is False
        assert body["auth_required"] is True


def test_api_requires_bearer_token(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        assert client.get("/api/model/info").status_code == 401
        ok = client.get("/api/model/info", headers=HEADERS)
        assert ok.status_code == 200
        assert ok.json()["loaded"] is False


def test_segment_without_model_returns_503(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    Image.new("RGB", (100, 80), (1, 2, 3)).save(image_path)
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/segment",
            headers=HEADERS,
            json={
                "image_path": str(image_path),
                "boxes": [{"x1": 10, "y1": 10, "x2": 50, "y2": 60}],
            },
        )
        assert response.status_code == 503


def test_model_load_missing_checkpoint_returns_404(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/model/load",
            headers=HEADERS,
            json={"checkpoint": str(tmp_path / "nope.pth")},
        )
        assert response.status_code == 404


def test_root_without_frontend(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["name"] == "Chizhi SegMentor API"
