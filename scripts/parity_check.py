#!/usr/bin/env python3
"""Compare the vendored predictor with the original model6ch forward pass.

This is the M0 numerical gate: for one real image + VOC box, the 6-channel
input and the 512x768 raw logits must match the training-time implementation.

Usage:
    python scripts/parity_check.py
    python scripts/parity_check.py --image ... --xml ...
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import torch
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
ORIGINAL_REPO = Path(os.environ.get("BOXMASK_ORIGINAL_REPO", "model6ch"))
DEFAULT_IMAGE = Path(os.environ.get("BOXMASK_PARITY_IMAGE", "data/tank_annotated/JPEGImages/DJI_20250307152100_0009__000010.jpg"))
DEFAULT_XML = Path(os.environ.get("BOXMASK_PARITY_XML", "data/tank_annotated/Annotations/DJI_20250307152100_0009__000010.xml"))
DEFAULT_CKPT = REPO / "models" / "boxmask_repvit_best_snapshot.pth"
DEFAULT_OUT = REPO / "backend" / "tests" / "fixtures"


def read_voc_box(xml_path: Path) -> tuple[float, float, float, float]:
    root = ET.parse(xml_path).getroot()
    obj = root.find("object")
    if obj is None:
        raise ValueError(f"no <object> in {xml_path}")
    bnd = obj.find("bndbox")
    assert bnd is not None
    xmin = float(bnd.findtext("xmin"))
    ymin = float(bnd.findtext("ymin"))
    xmax = float(bnd.findtext("xmax"))
    ymax = float(bnd.findtext("ymax"))
    # VOC xmax/ymax are inclusive; PIL crop's right/bottom are exclusive.
    return xmin, ymin, xmax + 1.0, ymax + 1.0


def load_original_module():
    """Load model6ch/repvit_pnet.py under a distinct module name."""

    path = ORIGINAL_REPO / "repvit_pnet.py"
    spec = importlib.util.spec_from_file_location("orig_repvit_pnet", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def original_preprocess(image: Image.Image, box: tuple[float, float, float, float]):
    """Independent copy of dataset.py's zoom=True path (no torchvision import)."""

    img = image.convert("RGB")
    W0, H0 = img.size
    x0, y0, x1, y1 = box
    x0 = max(0, min(W0, int(round(x0))))
    y0 = max(0, min(H0, int(round(y0))))
    x1 = max(0, min(W0, int(round(x1))))
    y1 = max(0, min(H0, int(round(y1))))
    if x1 - x0 < 2 or y1 - y0 < 2:
        x0, y0, x1, y1 = 0, 0, W0, H0

    crop = img.crop((x0, y0, x1, y1))
    W, H = 768, 512
    w, h = crop.size
    s = min(W / w, H / h)
    nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    canvas.paste(crop.resize((nw, nh), Image.BILINEAR), ((W - nw) // 2, (H - nh) // 2))

    img_s = img.resize((W, H), Image.BILINEAR)
    arr = np.concatenate([np.array(img_s), np.array(canvas)], axis=2)
    x = torch.from_numpy(np.ascontiguousarray(arr.transpose(2, 0, 1))).float().div_(255.0)
    x = x.unsqueeze(0)
    mean = torch.tensor([0.485, 0.456, 0.406] * 2).view(1, 6, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225] * 2).view(1, 6, 1, 1)
    return (x - mean) / std


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--xml", type=Path, default=DEFAULT_XML)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CKPT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--atol", type=float, default=1e-5)
    args = parser.parse_args()

    sys.path.insert(0, str(REPO / "backend"))
    from boxmask.inference.predictor import BoxMaskPredictor, build_input, prepare_image

    if not args.image.is_file():
        raise SystemExit(f"image not found: {args.image}")
    if not args.xml.is_file():
        raise SystemExit(f"xml not found: {args.xml}")
    if not args.checkpoint.is_file():
        raise SystemExit(f"checkpoint not found: {args.checkpoint}")

    image = Image.open(args.image)
    image.load()
    box = read_voc_box(args.xml)

    predictor = BoxMaskPredictor(args.checkpoint, device="cpu")
    predictor.load()
    rgb, full = prepare_image(image)
    x_new, info = build_input(rgb, full, box)
    logits_new = predictor.logits_from_tensor(x_new)

    original = load_original_module()
    net = original.RepViTPNet(weights=None)
    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    net.load_state_dict(state)
    net.eval()
    x_ref = original_preprocess(image, box)
    with torch.inference_mode():
        logits_ref = net(x_ref)[4].float().cpu()

    input_equal = torch.equal(x_new, x_ref)
    input_max_abs = float((x_new - x_ref).abs().max())
    logits_allclose = torch.allclose(logits_new, logits_ref, atol=args.atol, rtol=args.atol)
    logits_max_abs = float((logits_new - logits_ref).abs().max())

    args.out.mkdir(parents=True, exist_ok=True)
    np.save(args.out / "golden_input.npy", x_new.numpy())
    np.save(args.out / "golden_logits.npy", logits_new.numpy())
    meta = {
        "image": str(args.image),
        "xml": str(args.xml),
        "checkpoint": str(args.checkpoint),
        "checkpoint_sha256": predictor.model_hash,
        "box_xyxy": list(box),
        "box_used": [info.x1, info.y1, info.x2, info.y2],
        "fallback_full_image": info.fallback_full_image,
        "input_shape": list(x_new.shape),
        "input_equal": input_equal,
        "input_max_abs": input_max_abs,
        "logits_max_abs": logits_max_abs,
        "logits_allclose": logits_allclose,
        "atol": args.atol,
    }
    (args.out / "golden_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps(meta, ensure_ascii=False, indent=2))
    if not input_equal or not logits_allclose:
        print("PARITY CHECK FAILED", file=sys.stderr)
        return 1
    print("PARITY CHECK PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
