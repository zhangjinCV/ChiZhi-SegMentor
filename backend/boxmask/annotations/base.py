"""Shared types and helpers for annotation adapters."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


@dataclass
class BoxRecord:
    x1: float
    y1: float
    x2: float
    y2: float
    label: str = "object"
    confidence: float | None = None
    difficult: bool = False

    def normalized(self, width: int | None = None, height: int | None = None) -> BoxRecord | None:
        x1, y1, x2, y2 = self.x1, self.y1, self.x2, self.y2
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1
        if width is not None and height is not None:
            x1 = max(0.0, min(float(width), x1))
            y1 = max(0.0, min(float(height), y1))
            x2 = max(0.0, min(float(width), x2))
            y2 = max(0.0, min(float(height), y2))
        if x2 - x1 < 1 or y2 - y1 < 1:
            return None
        return BoxRecord(x1, y1, x2, y2, self.label, self.confidence, self.difficult)

    def as_dict(self) -> dict:
        return {
            "x1": round(self.x1, 2),
            "y1": round(self.y1, 2),
            "x2": round(self.x2, 2),
            "y2": round(self.y2, 2),
            "label": self.label,
            "confidence": self.confidence,
            "difficult": self.difficult,
        }


@dataclass
class ImageRecord:
    image_path: str | None
    name: str
    width: int | None = None
    height: int | None = None
    boxes: list[BoxRecord] = field(default_factory=list)
    source: str = ""
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "image_path": self.image_path,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "boxes": [box.as_dict() for box in self.boxes],
            "source": self.source,
            "warnings": self.warnings,
        }


@dataclass
class ParseResult:
    format: str
    records: list[ImageRecord]
    warnings: list[str] = field(default_factory=list)

    @property
    def image_count(self) -> int:
        return len(self.records)

    @property
    def box_count(self) -> int:
        return sum(len(record.boxes) for record in self.records)

    @property
    def missing_images(self) -> int:
        return sum(1 for record in self.records if not record.image_path)

    @property
    def empty_images(self) -> int:
        return sum(1 for record in self.records if record.image_path and not record.boxes)

    def as_dict(self, preview_limit: int | None = None) -> dict:
        records = self.records if preview_limit is None else self.records[:preview_limit]
        return {
            "format": self.format,
            "image_count": self.image_count,
            "box_count": self.box_count,
            "missing_images": self.missing_images,
            "empty_images": self.empty_images,
            "warnings": self.warnings[:50],
            "truncated": preview_limit is not None and len(self.records) > preview_limit,
            "records": [record.as_dict() for record in records],
        }


def image_size(path: Path) -> tuple[int | None, int | None]:
    try:
        with Image.open(path) as image:
            return image.size
    except Exception:
        return None, None


def iter_images(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in IMAGE_EXT else []
    if not root.is_dir():
        return []
    return sorted(
        path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXT
    )


def build_image_index(roots: Iterable[Path]) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    for root in roots:
        for path in iter_images(root):
            index.setdefault(path.name.lower(), []).append(path)
            try:
                rel = path.relative_to(root).as_posix().lower()
                index.setdefault(rel, []).append(path)
            except ValueError:
                pass
    return index


def resolve_image(
    name: str,
    bases: Iterable[Path],
    index: dict[str, list[Path]] | None = None,
    warnings: list[str] | None = None,
) -> Path | None:
    if not name:
        return None
    raw = Path(name)
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    for base in bases:
        candidates.append(base / name)
        candidates.append(base / raw.name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    if index:
        hits = index.get(raw.name.lower()) or index.get(name.replace("\\", "/").lower()) or []
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1 and warnings is not None:
            warnings.append(f"{name} 匹配到多个同名图片，已使用第一个")
            return hits[0]
    return None


def common_image_bases(annotation_path: Path, image_root: Path | None) -> list[Path]:
    bases: list[Path] = []
    if image_root is not None:
        bases.append(image_root)
    parent = annotation_path.parent
    bases.extend(
        [
            parent,
            parent / "JPEGImages",
            parent.parent / "JPEGImages",
            parent.parent,
        ]
    )
    return bases
