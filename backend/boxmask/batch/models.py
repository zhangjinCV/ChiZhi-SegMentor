from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..security import signed_file_url


@dataclass
class ItemResult:
    box_index: int
    label: str
    box: list[float]
    box_used: list[int]
    mask_path: str
    overlay_path: str
    area_px: int
    area_ratio: float
    mean_prob: float | None = None
    latency_ms: float = 0.0
    warning: str | None = None

    def as_dict(self, token: str | None = None) -> dict[str, Any]:
        data = {
            "box_index": self.box_index,
            "label": self.label,
            "box": self.box,
            "box_used": self.box_used,
            "mask_path": self.mask_path,
            "overlay_path": self.overlay_path,
            "area_px": self.area_px,
            "area_ratio": self.area_ratio,
            "mean_prob": self.mean_prob,
            "latency_ms": self.latency_ms,
            "warning": self.warning,
        }
        if token:
            data["mask_url"] = signed_file_url(token, self.mask_path)
            data["overlay_url"] = signed_file_url(token, self.overlay_path)
        return data


@dataclass
class BatchItem:
    index: int
    image_path: str | None
    name: str
    width: int | None
    height: int | None
    boxes: list[dict[str, Any]]
    status: str = "pending"
    attempts: int = 0
    error: str | None = None
    results: list[ItemResult] = field(default_factory=list)
    elapsed_ms: float | None = None

    def as_dict(self, token: str | None = None) -> dict[str, Any]:
        return {
            "index": self.index,
            "image_path": self.image_path,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "boxes": self.boxes,
            "status": self.status,
            "attempts": self.attempts,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
            "results": [result.as_dict(token) for result in self.results],
        }

    def to_manifest(self) -> dict[str, Any]:
        data = self.as_dict()
        return data

    @classmethod
    def from_manifest(cls, data: dict[str, Any]) -> BatchItem:
        results = [
            ItemResult(
                box_index=int(result.get("box_index", 0)),
                label=str(result.get("label", "object")),
                box=list(result.get("box") or []),
                box_used=list(result.get("box_used") or []),
                mask_path=str(result.get("mask_path", "")),
                overlay_path=str(result.get("overlay_path", "")),
                area_px=int(result.get("area_px", 0)),
                area_ratio=float(result.get("area_ratio", 0.0)),
                mean_prob=result.get("mean_prob"),
                latency_ms=float(result.get("latency_ms", 0.0)),
                warning=result.get("warning"),
            )
            for result in data.get("results", [])
        ]
        return cls(
            index=int(data.get("index", 0)),
            image_path=data.get("image_path"),
            name=str(data.get("name", "")),
            width=data.get("width"),
            height=data.get("height"),
            boxes=list(data.get("boxes") or []),
            status=str(data.get("status", "pending")),
            attempts=int(data.get("attempts", 0)),
            error=data.get("error"),
            results=results,
            elapsed_ms=data.get("elapsed_ms"),
        )


@dataclass
class BatchJob:
    id: str
    items: list[BatchItem]
    params: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    current_index: int | None = None
    stop_on_error: bool = False
    output_dir: str = ""
    error: str | None = None

    def counts(self) -> dict[str, Any]:
        total_images = len(self.items)
        total_boxes = sum(len(item.boxes) for item in self.items)
        done = sum(1 for item in self.items if item.status == "done")
        failed = sum(1 for item in self.items if item.status == "failed")
        skipped = sum(1 for item in self.items if item.status == "skipped")
        running = sum(1 for item in self.items if item.status == "running")
        pending = sum(1 for item in self.items if item.status == "pending")
        done_boxes = sum(len(item.results) for item in self.items)
        finished = done + failed + skipped
        return {
            "total_images": total_images,
            "total_boxes": total_boxes,
            "done_images": done,
            "failed_images": failed,
            "skipped_images": skipped,
            "running_images": running,
            "pending_images": pending,
            "done_boxes": done_boxes,
            "finished_images": finished,
            "progress": (finished / total_images) if total_images else 0.0,
        }

    def current_name(self) -> str | None:
        if self.current_index is None:
            return None
        for item in self.items:
            if item.index == self.current_index:
                return item.name
        return None

    def as_dict(
        self,
        token: str | None = None,
        include_items: bool = True,
        items_limit: int | None = None,
    ) -> dict[str, Any]:
        items = self.items if items_limit is None else self.items[:items_limit]
        data: dict[str, Any] = {
            "id": self.id,
            "status": self.status,
            "params": self.params,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "current_index": self.current_index,
            "current_name": self.current_name(),
            "error": self.error,
            "output_dir": self.output_dir,
            **self.counts(),
        }
        if include_items:
            data["items"] = [item.as_dict(token) for item in items]
            data["items_total"] = len(self.items)
        return data

    def to_manifest(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "params": self.params,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "current_index": self.current_index,
            "stop_on_error": self.stop_on_error,
            "output_dir": self.output_dir,
            "error": self.error,
            "items": [item.to_manifest() for item in self.items],
        }

    @classmethod
    def from_manifest(cls, data: dict[str, Any]) -> BatchJob:
        return cls(
            id=str(data.get("id", "")),
            items=[BatchItem.from_manifest(item) for item in data.get("items", [])],
            params=dict(data.get("params") or {}),
            status=str(data.get("status", "pending")),
            created_at=float(data.get("created_at", time.time())),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            current_index=data.get("current_index"),
            stop_on_error=bool(data.get("stop_on_error", False)),
            output_dir=str(data.get("output_dir", "")),
            error=data.get("error"),
        )

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "output_dir": self.output_dir,
            **self.counts(),
        }

    def result_paths(self) -> list[str]:
        return [result.mask_path for item in self.items for result in item.results]

    def output_path(self) -> Path:
        return Path(self.output_dir)
