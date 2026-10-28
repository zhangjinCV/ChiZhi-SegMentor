"""Box-prompted segmentation predictor.

The deployed model expects a 6-channel tensor:
    channels 0..2 = RGB stretched to 768x512
    channels 3..5 = the box crop, letterboxed to 768x512 on a black canvas

This mirrors ``dataset.py`` in the training repo exactly.  The final mask is
``net(x)[4]``; the other outputs are auxiliary heads.  Probabilities are
upsampled to the original image size before thresholding.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

from ..vendor.repvit_pnet import RepViTPNet

log = logging.getLogger(__name__)

INPUT_W, INPUT_H = 768, 512
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]

# CPU constants: normalize before moving the batch to CUDA/MPS.  Moving a
# quantized/constant tensor around after .to(device) is a common source of
# device-mismatch bugs.
_MEAN = torch.tensor(MEAN * 2, dtype=torch.float32).view(1, 6, 1, 1)
_STD = torch.tensor(STD * 2, dtype=torch.float32).view(1, 6, 1, 1)


@dataclass(frozen=True)
class Box:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    def as_tuple(self) -> tuple[float, float, float, float]:
        return self.x1, self.y1, self.x2, self.y2

    def to_list(self) -> list[float]:
        return [self.x1, self.y1, self.x2, self.y2]


@dataclass(frozen=True)
class BoxInfo:
    """The box actually used by the model, after clamping/fallback."""

    x1: int
    y1: int
    x2: int
    y2: int
    fallback_full_image: bool = False
    warning: str | None = None

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1


@dataclass
class Prediction:
    logits: torch.Tensor          # [1, 1, 512, 768] float32 CPU
    prob: np.ndarray              # H0 x W0 float32
    mask: np.ndarray              # H0 x W0 bool
    box_info: BoxInfo
    latency_ms: float
    model_hash: str
    device: str


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_device(device: str = "auto") -> torch.device:
    device = (device or "auto").lower()
    if device == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available in this build.")
    if device == "mps" and not (
        getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available()
    ):
        raise RuntimeError("MPS was requested but is not available.")
    return torch.device(device)


def clamp_box_int(box: Box | Sequence[float], width: int, height: int) -> BoxInfo:
    """Convert a user box to the integer, right/bottom-open box used by PIL.

    This is the inference counterpart of ``dataset.py::_jitter_bb``: clamp to
    the image, enforce a minimum size, and fall back to the full image when the
    box is degenerate.  The training code never crops outside the image.
    """

    vals = box.as_tuple() if isinstance(box, Box) else tuple(float(v) for v in box)
    if len(vals) != 4:
        raise ValueError("box must contain four values (x1, y1, x2, y2)")
    x1, y1, x2, y2 = vals
    if x1 > x2:
        x1, x2 = x2, x1
    if y1 > y2:
        y1, y2 = y2, y1

    x1 = max(0, min(width, int(round(x1))))
    y1 = max(0, min(height, int(round(y1))))
    x2 = max(0, min(width, int(round(x2))))
    y2 = max(0, min(height, int(round(y2))))

    if x2 - x1 < 2 or y2 - y1 < 2:
        return BoxInfo(
            0,
            0,
            width,
            height,
            fallback_full_image=True,
            warning="框太小或完全在图像外，已回退为整图。",
        )
    return BoxInfo(x1, y1, x2, y2)


def expand_box(box: Box | Sequence[float], padding: int) -> tuple[float, float, float, float]:
    """Expand a box by ``padding`` pixels on every side before clamping."""

    x1, y1, x2, y2 = box.as_tuple() if isinstance(box, Box) else tuple(float(v) for v in box)
    pad = max(0, int(padding))
    return x1 - pad, y1 - pad, x2 + pad, y2 + pad


def letterbox(im: Image.Image, size: tuple[int, int] = (INPUT_W, INPUT_H)) -> Image.Image:
    """Exact copy of ``dataset.py::_letterbox`` (bilinear, black, centered)."""

    W, H = size
    w, h = im.size
    scale = min(W / w, H / h)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    canvas.paste(im.resize((nw, nh), Image.BILINEAR), ((W - nw) // 2, (H - nh) // 2))
    return canvas


def prepare_image(image: Image.Image) -> tuple[Image.Image, np.ndarray]:
    """RGB image plus the stretched full-image branch (uint8 HWC)."""

    rgb = image.convert("RGB")
    full = rgb.resize((INPUT_W, INPUT_H), Image.BILINEAR)
    return rgb, np.asarray(full)


def build_input(
    rgb: Image.Image,
    full_branch: np.ndarray,
    box: Box | Sequence[float],
    padding: int = 0,
) -> tuple[torch.Tensor, BoxInfo]:
    """Build one normalized 6-channel tensor (CPU, float32)."""

    if padding:
        box = expand_box(box, padding)
    info = clamp_box_int(box, rgb.width, rgb.height)
    crop = letterbox(rgb.crop((info.x1, info.y1, info.x2, info.y2)))
    arr = np.concatenate([full_branch, np.asarray(crop)], axis=2)
    x = torch.from_numpy(np.ascontiguousarray(arr.transpose(2, 0, 1))).float().div_(255.0)
    x = x.unsqueeze(0)
    x = (x - _MEAN) / _STD
    return x, info


class BoxMaskPredictor:
    """Loaded once per process; safe to reuse for interactive and batch jobs."""

    def __init__(self, checkpoint: str | Path, device: str = "auto"):
        self.checkpoint = Path(checkpoint)
        self.device = resolve_device(device)
        self.model_hash = sha256_file(self.checkpoint)
        self.net: RepViTPNet | None = None
        self.load_seconds: float | None = None

    @property
    def is_loaded(self) -> bool:
        return self.net is not None

    def load(self) -> None:
        if self.net is not None:
            return
        if not self.checkpoint.is_file():
            raise FileNotFoundError(f"checkpoint not found: {self.checkpoint}")
        started = time.perf_counter()
        net = RepViTPNet(weights=None)
        state = torch.load(self.checkpoint, map_location="cpu", weights_only=True)
        net.load_state_dict(state)
        net.to(self.device).eval()
        self.net = net
        self.load_seconds = time.perf_counter() - started
        log.info(
            "loaded %s on %s in %.2fs (sha256=%s)",
            self.checkpoint.name,
            self.device,
            self.load_seconds,
            self.model_hash[:12],
        )

    def _require_net(self) -> RepViTPNet:
        if self.net is None:
            self.load()
        assert self.net is not None
        return self.net

    @torch.inference_mode()
    def logits_from_tensor(self, x: torch.Tensor) -> torch.Tensor:
        net = self._require_net()
        return net(x.to(self.device))[4].float().cpu()

    @torch.inference_mode()
    def logits_many(self, tensors: Iterable[torch.Tensor]) -> torch.Tensor:
        """Batched logits for several boxes of the same image (or several images)."""

        batch = torch.cat(list(tensors), dim=0)
        net = self._require_net()
        return net(batch.to(self.device))[4].float().cpu()

    def logits_for(
        self, image: Image.Image, box: Box | Sequence[float], padding: int = 0
    ) -> tuple[torch.Tensor, BoxInfo]:
        rgb, full = prepare_image(image)
        x, info = build_input(rgb, full, box, padding=padding)
        return self.logits_from_tensor(x), info

    def predict(
        self,
        image: Image.Image,
        box: Box | Sequence[float],
        threshold: float = 0.5,
        padding: int = 0,
    ) -> Prediction:
        started = time.perf_counter()
        logits, info = self.logits_for(image, box, padding=padding)
        prob = F.interpolate(
            torch.sigmoid(logits),
            size=(image.height, image.width),
            mode="bilinear",
            align_corners=False,
        )[0, 0]
        prob_np = prob.numpy().astype(np.float32, copy=False)
        return Prediction(
            logits=logits,
            prob=prob_np,
            mask=prob_np > float(threshold),
            box_info=info,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            model_hash=self.model_hash,
            device=str(self.device),
        )

    def predict_many(
        self,
        image: Image.Image,
        boxes: Sequence[Box | Sequence[float]],
        threshold: float = 0.5,
        padding: int = 0,
    ) -> list[Prediction]:
        """One image decode / full-branch resize, several box crops batched."""

        started = time.perf_counter()
        rgb, full = prepare_image(image)
        tensors: list[torch.Tensor] = []
        infos: list[BoxInfo] = []
        for box in boxes:
            x, info = build_input(rgb, full, box, padding=padding)
            tensors.append(x)
            infos.append(info)
        if not tensors:
            return []
        logits = self.logits_many(tensors)
        elapsed = (time.perf_counter() - started) * 1000.0
        per_item = elapsed / len(tensors)
        out: list[Prediction] = []
        for i, info in enumerate(infos):
            item_logits = logits[i : i + 1]
            prob = F.interpolate(
                torch.sigmoid(item_logits),
                size=(image.height, image.width),
                mode="bilinear",
                align_corners=False,
            )[0, 0]
            prob_np = prob.numpy().astype(np.float32, copy=False)
            out.append(
                Prediction(
                    logits=item_logits,
                    prob=prob_np,
                    mask=prob_np > float(threshold),
                    box_info=info,
                    latency_ms=per_item,
                    model_hash=self.model_hash,
                    device=str(self.device),
                )
            )
        return out

    def preview_branches(
        self, image: Image.Image, box: Box | Sequence[float], padding: int = 0
    ) -> tuple[Image.Image, Image.Image, BoxInfo]:
        """The two RGB branches shown in the UI's "model input preview"."""

        rgb, full = prepare_image(image)
        if padding:
            box = expand_box(box, padding)
        info = clamp_box_int(box, rgb.width, rgb.height)
        full_img = Image.fromarray(full, mode="RGB")
        crop_img = letterbox(rgb.crop((info.x1, info.y1, info.x2, info.y2)))
        return full_img, crop_img, info
