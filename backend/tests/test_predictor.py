from __future__ import annotations

import numpy as np
import torch
from boxmask.inference.mask_utils import (
    MaskPostprocess,
    apply_postprocess,
    cutout_rgba,
    mask_contours,
    mask_summary,
    overlay_image,
)
from boxmask.inference.predictor import (
    Box,
    build_input,
    clamp_box_int,
    letterbox,
    prepare_image,
)
from PIL import Image


def test_clamp_box_normal() -> None:
    info = clamp_box_int((10.4, 20.4, 100.6, 200.6), 300, 400)
    assert (info.x1, info.y1, info.x2, info.y2) == (10, 20, 101, 201)
    assert not info.fallback_full_image


def test_clamp_box_reversed_and_out_of_bounds() -> None:
    info = clamp_box_int((120, 250, -20, -5), 200, 300)
    assert (info.x1, info.y1, info.x2, info.y2) == (0, 0, 120, 250)
    assert not info.fallback_full_image


def test_clamp_box_degenerate_falls_back_to_full_image() -> None:
    info = clamp_box_int((10, 10, 10.5, 10.5), 320, 240)
    assert (info.x1, info.y1, info.x2, info.y2) == (0, 0, 320, 240)
    assert info.fallback_full_image
    assert info.warning


def test_letterbox_keeps_aspect_and_black_padding() -> None:
    image = Image.new("RGB", (400, 100), (255, 0, 0))
    out = letterbox(image)
    assert out.size == (768, 512)
    arr = np.asarray(out)
    # The resized crop is centered vertically: 400x100 -> 768x192, top pad 160.
    assert np.all(arr[0, 0] == 0)
    assert np.all(arr[160:352, 0] == np.array([255, 0, 0], dtype=np.uint8))
    assert np.all(arr[160, 0] == np.array([255, 0, 0], dtype=np.uint8))


def test_build_input_has_six_channels_and_expected_order() -> None:
    image = Image.new("RGB", (640, 480), (10, 20, 30))
    rgb, full = prepare_image(image)
    x, info = build_input(rgb, full, (20, 30, 300, 400))
    assert x.shape == (1, 6, 512, 768)
    assert x.dtype == torch.float32
    assert info.x1 == 20 and info.y1 == 30 and info.x2 == 300 and info.y2 == 400
    # Channel 3..5 must come from the crop branch, not the full image.
    assert not torch.allclose(x[0, 0], x[0, 3])


def test_mask_postprocess_and_previews() -> None:
    mask = np.zeros((100, 120), dtype=bool)
    mask[20:60, 30:80] = True
    mask[80:90, 10:20] = True
    params = MaskPostprocess(min_area=50, keep_largest=True, fill_holes=False, smooth_radius=0)
    cleaned = apply_postprocess(mask, params)
    assert cleaned.sum() == mask[20:60, 30:80].sum()
    assert mask_contours(cleaned)

    summary = mask_summary(cleaned)
    assert summary["area_px"] == cleaned.sum()
    assert 0 < summary["area_ratio"] < 1

    image = Image.new("RGB", (120, 100), (255, 255, 255))
    overlay = overlay_image(image, cleaned)
    assert overlay.size == image.size
    cutout = cutout_rgba(image, cleaned)
    assert cutout.mode == "RGBA"
    assert cutout.getpixel((30, 20))[3] == 255
    assert cutout.getpixel((0, 0))[3] == 0


def test_box_dataclass() -> None:
    box = Box(1, 2, 11, 22)
    assert box.width == 10
    assert box.height == 20
    assert box.to_list() == [1, 2, 11, 22]
