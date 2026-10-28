export type Tool = "select" | "draw" | "pan";
export type ViewMode = "overlay" | "original";

export interface EditorImage {
  id: string;
  path: string;
  name: string;
  url?: string;
  width?: number;
  height?: number;
  status: "loading" | "ready" | "error";
}

export interface EditorBox {
  id: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  label?: string;
}

export interface SegmentResult {
  boxId: string;
  maskBase64: string;
  overlayBase64?: string;
  areaPx: number;
  areaRatio: number;
  meanProb?: number;
  latencyMs: number;
  warning?: string;
  boxUsed: number[];
  fallbackFullImage: boolean;
}

export interface ModelInfo {
  loaded: boolean;
  checkpoint?: string;
  checkpoint_name?: string;
  checkpoint_size?: number;
  model_hash?: string;
  device?: string;
  load_seconds?: number;
  input_width: number;
  input_height: number;
  parameters_million: number;
}

export interface Health {
  status: string;
  version: string;
  model: ModelInfo;
  auth_required: boolean;
}

export interface SegmentResponse {
  image_path: string;
  width: number;
  height: number;
  model_hash: string;
  device: string;
  results: Array<{
    box: number[];
    box_used: number[];
    fallback_full_image: boolean;
    warning?: string | null;
    mask_png_base64: string;
    overlay_png_base64?: string | null;
    area_px: number;
    area_ratio: number;
    mean_prob?: number | null;
    latency_ms: number;
  }>;
}

export interface InputPreview {
  full_png_base64: string;
  crop_png_base64: string;
  box_used: number[];
  fallback_full_image: boolean;
  warning?: string | null;
}

export interface BatchBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  label?: string;
  confidence?: number | null;
  difficult?: boolean;
}

export interface BatchParseRecord {
  image_path: string | null;
  name: string;
  width?: number | null;
  height?: number | null;
  boxes: BatchBox[];
  source?: string;
  warnings: string[];
}

export interface BatchParseResponse {
  format: string;
  image_count: number;
  box_count: number;
  missing_images: number;
  empty_images: number;
  warnings: string[];
  truncated: boolean;
  records: BatchParseRecord[];
}

export interface BatchResultItem {
  box_index: number;
  label: string;
  box: number[];
  box_used: number[];
  mask_path: string;
  overlay_path: string;
  mask_url?: string;
  overlay_url?: string;
  area_px: number;
  area_ratio: number;
  mean_prob?: number | null;
  latency_ms: number;
  warning?: string | null;
}

export interface BatchJobItem {
  index: number;
  image_path: string | null;
  name: string;
  width?: number | null;
  height?: number | null;
  boxes: BatchBox[];
  status: string;
  attempts: number;
  error?: string | null;
  elapsed_ms?: number | null;
  results: BatchResultItem[];
}

export interface BatchJobSummary {
  id: string;
  status: string;
  created_at: number;
  finished_at?: number | null;
  output_dir: string;
  total_images: number;
  total_boxes: number;
  done_images: number;
  failed_images: number;
  skipped_images: number;
  running_images: number;
  pending_images: number;
  done_boxes: number;
  finished_images: number;
  progress: number;
}

export interface BatchJob extends BatchJobSummary {
  params?: Record<string, unknown>;
  current_index?: number | null;
  current_name?: string | null;
  error?: string | null;
  items?: BatchJobItem[];
  items_total?: number;
}
