from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from ..annotations import parse_annotations
from ..image_io import load_image
from ..inference import MaskPostprocess, apply_postprocess, mask_summary, overlay_image, save_mask_png
from ..settings import RuntimeSettings
from .models import BatchItem, BatchJob, ItemResult

log = logging.getLogger(__name__)


def _safe_name(value: str, fallback: str = "image") -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", value, flags=re.UNICODE).strip("._")
    return cleaned or fallback


def _error_text(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if detail:
        return str(detail)
    return str(exc) or exc.__class__.__name__


class BatchManager:
    """Single-worker batch runner.

    One job runs at a time.  Pause/resume is cooperative: the worker finishes
    the current image, then waits.  Results are written to disk after every
    image so an interrupted job can be inspected or resumed.
    """

    def __init__(self, settings: RuntimeSettings, models: Any):
        self.settings = settings
        self.models = models
        self.jobs_dir = settings.data_dir / "batch"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, BatchJob] = {}
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._active_job_id: str | None = None
        self._load_existing()

    # ------------------------------------------------------------------ storage
    def _job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / job_id

    def _manifest_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "job.json"

    def _save(self, job: BatchJob) -> None:
        try:
            path = self._manifest_path(job.id)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(job.to_manifest(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(path)
        except Exception:
            log.exception("failed to save batch manifest %s", job.id)

    def _load_existing(self) -> None:
        for manifest in self.jobs_dir.glob("*/job.json"):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                job = BatchJob.from_manifest(data)
                if job.status in {"running", "paused"}:
                    job.status = "interrupted"
                for item in job.items:
                    if item.status == "running":
                        item.status = "pending"
                self.jobs[job.id] = job
            except Exception:
                log.exception("failed to load batch manifest %s", manifest)

    # ------------------------------------------------------------------ parse
    def parse(
        self,
        annotation_path: str,
        annotation_format: str = "auto",
        image_root: str | None = None,
    ):
        return parse_annotations(annotation_path, annotation_format, image_root)

    # ------------------------------------------------------------------ create
    def create_job(
        self,
        records: list[dict[str, Any]],
        params: dict[str, Any],
        stop_on_error: bool = False,
        label_filter: list[str] | None = None,
        skip_empty: bool = True,
    ) -> BatchJob:
        job_id = uuid.uuid4().hex[:12]
        output_dir = self._job_dir(job_id)
        (output_dir / "masks").mkdir(parents=True, exist_ok=True)
        (output_dir / "overlays").mkdir(parents=True, exist_ok=True)

        allowed = {str(label) for label in label_filter} if label_filter else None
        items: list[BatchItem] = []
        for index, record in enumerate(records):
            boxes = list(record.get("boxes") or [])
            if allowed is not None:
                boxes = [box for box in boxes if str(box.get("label", "object")) in allowed]
            image_path = record.get("image_path")
            status = "pending"
            error = None
            if not image_path:
                status = "failed"
                error = "找不到图片"
            elif skip_empty and not boxes:
                status = "skipped"
                error = "无框"
            items.append(
                BatchItem(
                    index=index,
                    image_path=str(image_path) if image_path else None,
                    name=str(record.get("name") or Path(str(image_path or index)).name),
                    width=record.get("width"),
                    height=record.get("height"),
                    boxes=boxes,
                    status=status,
                    error=error,
                )
            )

        if not any(item.status == "pending" for item in items):
            raise ValueError("没有可处理的图片（检查配对、类别过滤或框是否为空）")

        job = BatchJob(
            id=job_id,
            items=items,
            params=params,
            status="pending",
            stop_on_error=stop_on_error,
            output_dir=str(output_dir),
        )
        with self._lock:
            self.jobs[job.id] = job
            self._save(job)
        return job

    # ------------------------------------------------------------------ control
    def start(self, job_id: str) -> BatchJob:
        with self._lock:
            job = self._require(job_id)
            if self._thread and self._thread.is_alive():
                raise RuntimeError("已有批量任务在运行，请先暂停或等待完成")
            if job.status in {"completed", "cancelled"} and not any(
                item.status == "pending" for item in job.items
            ):
                raise RuntimeError("任务没有待处理项")
            job.status = "running"
            job.error = None
            job.started_at = job.started_at or time.time()
            job.finished_at = None
            for item in job.items:
                if item.status == "running":
                    item.status = "pending"
            self._active_job_id = job.id
            self._save(job)
            thread = threading.Thread(target=self._run, args=(job,), daemon=True)
            self._thread = thread
            thread.start()
            return job

    def pause(self, job_id: str) -> BatchJob:
        with self._lock:
            job = self._require(job_id)
            if job.status == "running":
                job.status = "paused"
                self._save(job)
            return job

    def resume(self, job_id: str) -> BatchJob:
        with self._lock:
            job = self._require(job_id)
            if job.status not in {"paused", "interrupted"}:
                return job
            job.status = "running"
            self._save(job)
            if self._thread is None or not self._thread.is_alive():
                self._active_job_id = job.id
                thread = threading.Thread(target=self._run, args=(job,), daemon=True)
                self._thread = thread
                thread.start()
            return job

    def cancel(self, job_id: str) -> BatchJob:
        with self._lock:
            job = self._require(job_id)
            if job.status in {"running", "paused", "interrupted", "pending"}:
                job.status = "cancelled"
                job.finished_at = time.time()
                self._save(job)
            return job

    def retry_failed(self, job_id: str) -> BatchJob:
        with self._lock:
            job = self._require(job_id)
            reset = 0
            for item in job.items:
                if item.status == "failed":
                    item.status = "pending"
                    item.error = None
                    item.results = []
                    reset += 1
            if not reset:
                raise RuntimeError("没有失败项可重试")
            job.status = "paused" if self._thread and self._thread.is_alive() else "running"
            job.finished_at = None
            job.error = None
            self._save(job)
            if self._thread is None or not self._thread.is_alive():
                self._active_job_id = job.id
                thread = threading.Thread(target=self._run, args=(job,), daemon=True)
                self._thread = thread
                thread.start()
            return job

    def _require(self, job_id: str) -> BatchJob:
        job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(f"任务不存在：{job_id}")
        return job

    # ------------------------------------------------------------------ worker
    def _run(self, job: BatchJob) -> None:
        try:
            for item in job.items:
                while job.status == "paused":
                    time.sleep(0.25)
                if job.status in {"cancelled", "failed"}:
                    break
                if item.status != "pending":
                    continue
                self._run_item(job, item)
                if job.status == "failed":
                    break
            with self._lock:
                if job.status == "running":
                    done = any(item.status == "done" for item in job.items)
                    job.status = "completed" if done else "failed"
                    if job.status == "failed" and not job.error:
                        job.error = "没有成功处理的图片"
                    job.finished_at = time.time()
                    job.current_index = None
                    self._save(job)
        except Exception as exc:  # defensive: never leave a job "running" silently
            log.exception("batch worker crashed")
            with self._lock:
                job.status = "failed"
                job.error = _error_text(exc)
                job.finished_at = time.time()
                self._save(job)
        finally:
            with self._lock:
                if self._active_job_id == job.id:
                    self._active_job_id = None

    def _run_item(self, job: BatchJob, item: BatchItem) -> None:
        started = time.perf_counter()
        with self._lock:
            item.status = "running"
            item.attempts += 1
            item.error = None
            item.results = []
            job.current_index = item.index
            self._save(job)

        try:
            if not item.image_path:
                raise FileNotFoundError("找不到图片")
            image = load_image(item.image_path)
            item.width, item.height = image.size
            if not item.boxes:
                raise ValueError("无框")
            params = job.params
            threshold = float(params.get("threshold", 0.5))
            padding = int(params.get("padding", 0))
            pp = params.get("postprocess") or {}
            postprocess = MaskPostprocess(
                min_area=int(pp.get("min_area", 0)),
                keep_largest=bool(pp.get("keep_largest", False)),
                fill_holes=bool(pp.get("fill_holes", False)),
                smooth_radius=int(pp.get("smooth_radius", 0)),
            )
            boxes = [
                (float(box["x1"]), float(box["y1"]), float(box["x2"]), float(box["y2"]))
                for box in item.boxes
            ]
            predictions = self.models.predict_many(image, boxes, threshold, padding)
            if len(predictions) != len(item.boxes):
                raise RuntimeError("模型返回数量与框数量不一致")

            stem = _safe_name(Path(item.image_path).stem)
            image_dir = Path(job.output_dir) / "masks" / f"{item.index:05d}_{stem}"
            image_dir.mkdir(parents=True, exist_ok=True)
            overlay_dir = Path(job.output_dir) / "overlays"
            overlay_dir.mkdir(parents=True, exist_ok=True)

            for box_index, (prediction, source_box) in enumerate(
                zip(predictions, item.boxes, strict=False)
            ):
                mask = apply_postprocess(prediction.mask, postprocess)
                summary = mask_summary(mask, prediction.prob)
                mask_path = image_dir / f"box_{box_index:02d}.png"
                overlay_path = overlay_dir / f"{item.index:05d}_{stem}_box_{box_index:02d}.png"
                save_mask_png(mask, mask_path)
                overlay_image(image, mask, alpha=1.0).save(overlay_path, format="PNG")
                item.results.append(
                    ItemResult(
                        box_index=box_index,
                        label=str(source_box.get("label", "object")),
                        box=[
                            float(source_box.get("x1", 0)),
                            float(source_box.get("y1", 0)),
                            float(source_box.get("x2", 0)),
                            float(source_box.get("y2", 0)),
                        ],
                        box_used=[
                            prediction.box_info.x1,
                            prediction.box_info.y1,
                            prediction.box_info.x2,
                            prediction.box_info.y2,
                        ],
                        mask_path=str(mask_path),
                        overlay_path=str(overlay_path),
                        area_px=summary["area_px"],
                        area_ratio=summary["area_ratio"],
                        mean_prob=summary.get("mean_prob"),
                        latency_ms=prediction.latency_ms,
                        warning=prediction.box_info.warning,
                    )
                )
            item.status = "done"
            item.elapsed_ms = (time.perf_counter() - started) * 1000.0
            item.error = None
        except Exception as exc:
            item.status = "failed"
            item.error = _error_text(exc)
            item.elapsed_ms = (time.perf_counter() - started) * 1000.0
            log.warning("batch item %s failed: %s", item.image_path, item.error)
            if job.stop_on_error:
                job.status = "failed"
                job.error = f"{item.name}: {item.error}"
        finally:
            with self._lock:
                self._save(job)

    # ------------------------------------------------------------------ read
    def status(
        self, job_id: str, token: str | None = None, include_items: bool = True
    ) -> dict[str, Any]:
        with self._lock:
            job = self._require(job_id)
            return job.as_dict(token=token, include_items=include_items)

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                job.summary()
                for job in sorted(self.jobs.values(), key=lambda item: item.created_at, reverse=True)
            ]

    def export(self, job_id: str, dest_dir: str | None, formats: list[str], naming: str | None):
        from .export import export_job

        with self._lock:
            job = self._require(job_id)
        return export_job(job, dest_dir, formats, naming)
