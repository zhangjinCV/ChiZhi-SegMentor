"""Mask post-processing, contours, previews and export helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

try:  # OpenCV is optional at import time; inference itself only needs torch/PIL.
    import cv2
except Exception:  # pragma: no cover - exercised on machines without OpenCV
    cv2 = None


@dataclass(frozen=True)
class MaskPostprocess:
    """Optional cleanup applied after thresholding.

    Defaults are all off so the exported mask matches the model's raw output.
    """

    min_area: int = 0
    keep_largest: bool = False
    fill_holes: bool = False
    smooth_radius: int = 0

    @property
    def is_noop(self) -> bool:
        return not (self.min_area or self.keep_largest or self.fill_holes or self.smooth_radius)


def _as_u8(mask: np.ndarray) -> np.ndarray:
    return (mask.astype(np.uint8) > 0).astype(np.uint8)


def apply_postprocess(mask: np.ndarray, params: MaskPostprocess | None) -> np.ndarray:
    if params is None or params.is_noop:
        return mask.astype(bool, copy=False)
    if cv2 is None:
        raise RuntimeError("OpenCV is required for mask post-processing.")

    m = _as_u8(mask)
    if params.smooth_radius > 0:
        r = max(1, int(params.smooth_radius))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kernel)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel)

    if params.fill_holes:
        h, w = m.shape
        padded = np.pad(m, 1, mode="constant", constant_values=0)
        flood = padded.copy()
        flood_mask = np.zeros((h + 4, w + 4), np.uint8)
        cv2.floodFill(flood, flood_mask, (0, 0), 1)
        holes = (flood[1:-1, 1:-1] == 0).astype(np.uint8)
        m = np.maximum(m, holes)

    if params.min_area > 0 or params.keep_largest:
        n, labels, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        if n > 1:
            areas = stats[1:, cv2.CC_STAT_AREA]
            keep = np.zeros(n, bool)
            if params.keep_largest and len(areas):
                keep[1 + int(np.argmax(areas))] = True
            else:
                keep[1:] = areas >= int(params.min_area)
            m = keep[labels].astype(np.uint8)

    return m.astype(bool)


def mask_area(mask: np.ndarray) -> int:
    return int(np.count_nonzero(mask))


def mask_contours(mask: np.ndarray, epsilon: float = 1.5) -> list[list[list[float]]]:
    """Outer contours for UI overlays and COCO/LabelMe export."""

    if cv2 is None or not mask.any():
        return []
    contours, _ = cv2.findContours(_as_u8(mask), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    polygons: list[list[list[float]]] = []
    for contour in contours:
        if cv2.contourArea(contour) < 1:
            continue
        if epsilon > 0:
            contour = cv2.approxPolyDP(contour, float(epsilon), True)
        pts = contour.reshape(-1, 2)
        if len(pts) >= 3:
            polygons.append([[float(x), float(y)] for x, y in pts])
    return polygons


def save_mask_png(mask: np.ndarray, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((_as_u8(mask) * 255), mode="L").save(path)
    return path


def overlay_image(
    image: Image.Image,
    mask: np.ndarray,
    color: tuple[int, int, int] = (34, 211, 238),
    alpha: float = 0.45,
) -> Image.Image:
    """RGBA preview: original image with a translucent tinted mask."""

    rgba = image.convert("RGBA")
    tint = Image.new("RGBA", rgba.size, (*color, 0))
    alpha_mask = Image.fromarray((_as_u8(mask) * int(max(0.0, min(1.0, alpha)) * 255)).astype(np.uint8), mode="L")
    tint.putalpha(alpha_mask)
    return Image.alpha_composite(rgba, tint)


def cutout_rgba(image: Image.Image, mask: np.ndarray) -> Image.Image:
    rgba = image.convert("RGBA")
    alpha = Image.fromarray((_as_u8(mask) * 255), mode="L")
    rgba.putalpha(alpha)
    return rgba


def mask_summary(mask: np.ndarray, prob: np.ndarray | None = None) -> dict[str, Any]:
    total = int(mask.size)
    area = mask_area(mask)
    out: dict[str, Any] = {"area_px": area, "area_ratio": (area / total) if total else 0.0}
    if prob is not None and area:
        out["mean_prob"] = float(np.asarray(prob)[mask].mean())
    return out
