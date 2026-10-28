from __future__ import annotations

from pydantic import BaseModel, Field


class BoxIn(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return self.x1, self.y1, self.x2, self.y2


class PostprocessIn(BaseModel):
    min_area: int = Field(default=0, ge=0)
    keep_largest: bool = False
    fill_holes: bool = False
    smooth_radius: int = Field(default=0, ge=0, le=64)


class SegmentRequest(BaseModel):
    image_path: str
    boxes: list[BoxIn] = Field(min_length=1, max_length=200)
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    padding: int = Field(default=0, ge=0, le=512)
    postprocess: PostprocessIn = Field(default_factory=PostprocessIn)
    include_probability: bool = False


class SegmentItem(BaseModel):
    box: list[float]
    box_used: list[int]
    fallback_full_image: bool = False
    warning: str | None = None
    mask_png_base64: str
    overlay_png_base64: str | None = None
    area_px: int
    area_ratio: float
    mean_prob: float | None = None
    latency_ms: float


class SegmentResponse(BaseModel):
    image_path: str
    width: int
    height: int
    model_hash: str
    device: str
    results: list[SegmentItem]


class ModelInfo(BaseModel):
    loaded: bool
    checkpoint: str | None = None
    checkpoint_name: str | None = None
    checkpoint_size: int | None = None
    model_hash: str | None = None
    device: str | None = None
    load_seconds: float | None = None
    input_width: int = 768
    input_height: int = 512
    parameters_million: float = 10.33


class HealthResponse(BaseModel):
    status: str
    version: str
    model: ModelInfo
    auth_required: bool = True


class ModelLoadRequest(BaseModel):
    checkpoint: str | None = None
    device: str | None = None


class ModelLoadResponse(BaseModel):
    model: ModelInfo


class InputPreviewResponse(BaseModel):
    full_png_base64: str
    crop_png_base64: str
    box_used: list[int]
    fallback_full_image: bool = False
    warning: str | None = None


class FileSignResponse(BaseModel):
    url: str
    expires_at: int


class BatchParseRequest(BaseModel):
    annotation_path: str
    annotation_format: str = "auto"
    image_root: str | None = None
    preview_limit: int = Field(default=200, ge=1, le=5000)


class BatchRunRequest(BaseModel):
    annotation_path: str
    annotation_format: str = "auto"
    image_root: str | None = None
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    padding: int = Field(default=0, ge=0, le=512)
    postprocess: PostprocessIn = Field(default_factory=PostprocessIn)
    label_filter: list[str] | None = None
    skip_empty: bool = True
    stop_on_error: bool = False


class BatchExportRequest(BaseModel):
    dest_dir: str | None = None
    formats: list[str] = Field(default_factory=lambda: ["mask"])
    naming: str | None = None
