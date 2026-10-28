from __future__ import annotations

import base64
import io
import logging
import mimetypes
import threading
import time
import uuid
from collections.abc import Iterable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError

from .. import __version__
from ..batch import BatchManager
from ..image_io import load_image
from ..inference import BoxMaskPredictor, MaskPostprocess, apply_postprocess, mask_summary, overlay_image
from ..security import make_signed_url, normalize_path, verify_signature
from ..settings import RuntimeSettings
from .schemas import (
    BatchExportRequest,
    BatchParseRequest,
    BatchRunRequest,
    FileSignResponse,
    HealthResponse,
    InputPreviewResponse,
    ModelInfo,
    ModelLoadRequest,
    ModelLoadResponse,
    SegmentItem,
    SegmentRequest,
    SegmentResponse,
)

log = logging.getLogger(__name__)


class ModelManager:
    """Owns the loaded predictor and serializes inference calls."""

    def __init__(self, settings: RuntimeSettings):
        self.settings = settings
        self._state_lock = threading.RLock()
        self._infer_lock = threading.Lock()
        self.predictor: BoxMaskPredictor | None = None

    def load_initial(self) -> None:
        try:
            self.load()
        except Exception:
            log.exception("initial model load failed; the API will start without a model")

    def load(self, checkpoint: str | None = None, device: str | None = None) -> ModelInfo:
        path = Path(checkpoint).expanduser() if checkpoint else self.settings.model_path
        target_device = device or self.settings.device
        with self._state_lock:
            predictor = BoxMaskPredictor(path, device=target_device)
            predictor.load()
            self.predictor = predictor
            self.settings.model_path = path
            self.settings.device = str(predictor.device)
        return self.info()

    def info(self) -> ModelInfo:
        with self._state_lock:
            predictor = self.predictor
        if predictor is None:
            return ModelInfo(
                loaded=False,
                checkpoint=str(self.settings.model_path),
                checkpoint_name=self.settings.model_path.name,
            )
        try:
            size = predictor.checkpoint.stat().st_size
        except OSError:
            size = None
        return ModelInfo(
            loaded=predictor.is_loaded,
            checkpoint=str(predictor.checkpoint),
            checkpoint_name=predictor.checkpoint.name,
            checkpoint_size=size,
            model_hash=predictor.model_hash,
            device=str(predictor.device),
            load_seconds=predictor.load_seconds,
        )

    def predict_many(self, image: Image.Image, boxes: Iterable, threshold: float, padding: int = 0):
        with self._state_lock:
            predictor = self.predictor
        if predictor is None:
            raise HTTPException(status_code=503, detail="模型尚未加载，请先在设置中选择 checkpoint。")
        with self._infer_lock:
            return predictor.predict_many(image, list(boxes), threshold=threshold, padding=padding)

    def preview(self, image: Image.Image, box, padding: int = 0):
        with self._state_lock:
            predictor = self.predictor
        if predictor is None:
            raise HTTPException(status_code=503, detail="模型尚未加载，请先在设置中选择 checkpoint。")
        with self._infer_lock:
            return predictor.preview_branches(image, box, padding=padding)


class AppState:
    def __init__(self, settings: RuntimeSettings):
        self.settings = settings
        self.models = ModelManager(settings)
        self.batch = BatchManager(settings, self.models)


def _png_base64(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _load_image(path: str) -> Image.Image:
    p = Path(path).expanduser()
    if not p.is_file():
        raise HTTPException(status_code=404, detail=f"图片不存在：{p}")
    try:
        return load_image(p)
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=400, detail=f"无法识别的图片格式：{p.name}") from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"图片读取失败：{p.name}（{exc}）") from exc


def _is_loopback_origin(origin: str) -> bool:
    return origin.startswith("http://127.0.0.1:") or origin.startswith("http://localhost:")


def create_app(settings: RuntimeSettings) -> FastAPI:
    state = AppState(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state.models.load_initial()
        yield

    app = FastAPI(
        title="Chizhi SegMentor API",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.boxmask = state

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and not _is_loopback_origin(origin):
                return JSONResponse(status_code=403, content={"detail": "origin not allowed"})
            host = request.headers.get("host", "")
            hostname = host.split(":", 1)[0]
            if hostname not in {"127.0.0.1", "localhost", "testserver"}:
                return JSONResponse(status_code=403, content={"detail": "host not allowed"})
            if (
                request.method != "OPTIONS"
                and path not in {"/api/health", "/api/file"}
                and not settings.dev_mode
            ):
                expected = f"Bearer {settings.token}"
                if request.headers.get("authorization") != expected:
                    return JSONResponse(status_code=401, content={"detail": "missing or invalid token"})
        return await call_next(request)

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=__version__,
            model=state.models.info(),
            auth_required=not settings.dev_mode,
        )

    @app.post("/api/model/load", response_model=ModelLoadResponse)
    def load_model(body: ModelLoadRequest) -> ModelLoadResponse:
        try:
            info = state.models.load(body.checkpoint, body.device)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            log.exception("model load failed")
            raise HTTPException(status_code=500, detail=f"模型加载失败：{exc}") from exc
        return ModelLoadResponse(model=info)

    @app.get("/api/model/info", response_model=ModelInfo)
    def model_info() -> ModelInfo:
        return state.models.info()

    @app.post("/api/segment", response_model=SegmentResponse)
    def segment(body: SegmentRequest) -> SegmentResponse:
        image = _load_image(body.image_path)
        boxes = [b.as_tuple() for b in body.boxes]
        predictions = state.models.predict_many(
            image, boxes, body.threshold, padding=body.padding
        )
        pp = MaskPostprocess(
            min_area=body.postprocess.min_area,
            keep_largest=body.postprocess.keep_largest,
            fill_holes=body.postprocess.fill_holes,
            smooth_radius=body.postprocess.smooth_radius,
        )
        results: list[SegmentItem] = []
        for pred in predictions:
            mask = apply_postprocess(pred.mask, pp)
            summary = mask_summary(mask, pred.prob)
            mask_img = Image.fromarray((mask.astype("uint8") * 255), mode="L")
            results.append(
                SegmentItem(
                    box=list(boxes[len(results)]),
                    box_used=[pred.box_info.x1, pred.box_info.y1, pred.box_info.x2, pred.box_info.y2],
                    fallback_full_image=pred.box_info.fallback_full_image,
                    warning=pred.box_info.warning,
                    mask_png_base64=_png_base64(mask_img),
                    overlay_png_base64=_png_base64(overlay_image(image, mask, alpha=1.0)),
                    area_px=summary["area_px"],
                    area_ratio=summary["area_ratio"],
                    mean_prob=summary.get("mean_prob"),
                    latency_ms=pred.latency_ms,
                )
            )
        return SegmentResponse(
            image_path=str(Path(body.image_path).expanduser()),
            width=image.width,
            height=image.height,
            model_hash=predictions[0].model_hash if predictions else "",
            device=predictions[0].device if predictions else str(settings.device),
            results=results,
        )

    @app.get("/api/model/input-preview", response_model=InputPreviewResponse)
    def input_preview(
        image_path: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        padding: int = 0,
    ) -> InputPreviewResponse:
        image = _load_image(image_path)
        full_img, crop_img, info = state.models.preview(
            image, (x1, y1, x2, y2), padding=padding
        )
        return InputPreviewResponse(
            full_png_base64=_png_base64(full_img),
            crop_png_base64=_png_base64(crop_img),
            box_used=[info.x1, info.y1, info.x2, info.y2],
            fallback_full_image=info.fallback_full_image,
            warning=info.warning,
        )

    @app.post("/api/batch/parse")
    def batch_parse(body: BatchParseRequest):
        try:
            result = state.batch.parse(
                body.annotation_path,
                body.annotation_format,
                body.image_root,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result.as_dict(preview_limit=body.preview_limit)

    @app.post("/api/batch/run")
    def batch_run(body: BatchRunRequest):
        try:
            result = state.batch.parse(
                body.annotation_path,
                body.annotation_format,
                body.image_root,
            )
            records = [record.as_dict() for record in result.records]
            params = {
                "threshold": body.threshold,
                "padding": body.padding,
                "postprocess": {
                    "min_area": body.postprocess.min_area,
                    "keep_largest": body.postprocess.keep_largest,
                    "fill_holes": body.postprocess.fill_holes,
                    "smooth_radius": body.postprocess.smooth_radius,
                },
            }
            job = state.batch.create_job(
                records,
                params,
                stop_on_error=body.stop_on_error,
                label_filter=body.label_filter,
                skip_empty=body.skip_empty,
            )
            state.batch.start(job.id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return state.batch.status(job.id, settings.token)

    @app.get("/api/batch/jobs")
    def batch_jobs():
        return {"jobs": state.batch.list_jobs()}

    @app.get("/api/batch/jobs/{job_id}")
    def batch_job(job_id: str, items: bool = True):
        try:
            return state.batch.status(job_id, settings.token, include_items=items)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/batch/jobs/{job_id}/pause")
    def batch_pause(job_id: str):
        try:
            state.batch.pause(job_id)
            return state.batch.status(job_id, settings.token)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/batch/jobs/{job_id}/resume")
    def batch_resume(job_id: str):
        try:
            state.batch.resume(job_id)
            return state.batch.status(job_id, settings.token)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/batch/jobs/{job_id}/cancel")
    def batch_cancel(job_id: str):
        try:
            state.batch.cancel(job_id)
            return state.batch.status(job_id, settings.token)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/batch/jobs/{job_id}/retry")
    def batch_retry(job_id: str):
        try:
            state.batch.retry_failed(job_id)
            return state.batch.status(job_id, settings.token)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/batch/jobs/{job_id}/export")
    def batch_export(job_id: str, body: BatchExportRequest):
        try:
            return state.batch.export(job_id, body.dest_dir, body.formats, body.naming)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"导出失败：{exc}") from exc

    @app.post("/api/upload")
    async def upload(request: Request, name: str = "image"):
        data = await request.body()
        if not data:
            raise HTTPException(status_code=400, detail="空文件")
        if len(data) > 100 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="文件超过 100MB")
        safe_name = Path(name).name or "image"
        dest_dir = settings.data_dir / "uploads"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{uuid.uuid4().hex}_{safe_name}"
        dest.write_bytes(data)
        return {"path": str(dest), "name": safe_name, "size": len(data)}

    @app.get("/api/file/sign", response_model=FileSignResponse)
    def sign_file(path: str, expires_in: int = 3600) -> FileSignResponse:
        p = Path(path).expanduser()
        if not p.is_file():
            raise HTTPException(status_code=404, detail=f"文件不存在：{p}")
        url, expires = make_signed_url(settings.token, p, expires_in)
        return FileSignResponse(url=url, expires_at=expires)

    @app.get("/api/file")
    def serve_file(path: str, expires: int, sig: str):
        if expires < int(time.time()):
            raise HTTPException(status_code=410, detail="链接已过期")
        if not verify_signature(settings.token, path, expires, sig):
            raise HTTPException(status_code=403, detail="签名无效")
        normalized = normalize_path(path)
        p = Path(normalized)
        if not p.is_file():
            raise HTTPException(status_code=404, detail=f"文件不存在：{p}")
        media_type = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        return FileResponse(p, media_type=media_type)

    @app.get("/api/overlay")
    def overlay(image_path: str):
        # Placeholder for the project/export flow; kept out of the M0 UI.
        _ = image_path
        raise HTTPException(status_code=501, detail="overlay preview is not implemented yet")

    if settings.web_dist and settings.web_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(settings.web_dist), html=True), name="web")
    else:

        @app.get("/")
        def root():
            return {
                "name": "Chizhi SegMentor API",
                "version": __version__,
                "message": "Frontend is not built yet. Use the Vite dev server in development.",
            }

    return app
