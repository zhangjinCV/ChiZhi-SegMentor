import type {
  BatchJob,
  BatchJobSummary,
  BatchParseResponse,
  EditorBox,
  Health,
  InputPreview,
  ModelInfo,
  SegmentResponse,
} from "../types";

export interface DesktopBridge {
  apiBase: string;
  token: string;
  platform: string;
  selectImages(): Promise<string[]>;
  selectFolder(): Promise<string | null>;
  selectAnnotationFile(): Promise<string | null>;
  getPathForFile(file: File): string;
  revealFile(path: string): Promise<void>;
  openLogs(): Promise<void>;
}

declare global {
  interface Window {
    boxmask?: DesktopBridge;
  }
}

const bridge = typeof window !== "undefined" ? window.boxmask : undefined;

export const API_BASE = (
  bridge?.apiBase ??
  window.localStorage.getItem("boxmask.apiBase") ??
  "http://127.0.0.1:8765"
).replace(/\/+$/, "");

export const TOKEN =
  bridge?.token ?? window.localStorage.getItem("boxmask.token") ?? "";

function authHeaders(): Headers {
  const headers = new Headers();
  if (TOKEN) headers.set("Authorization", `Bearer ${TOKEN}`);
  return headers;
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = authHeaders();
  const incoming = new Headers(init.headers);
  incoming.forEach((value, key) => headers.set(key, value));
  if (init.body && !(init.body instanceof Blob) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch (error) {
    throw new Error(`无法连接后端（${API_BASE}）。请确认 sidecar 已启动。`);
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail) detail = JSON.stringify(body.detail);
    } catch {
      // keep the HTTP status text
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export async function getHealth(): Promise<Health> {
  return apiFetch<Health>("/api/health");
}

export async function getModelInfo(): Promise<ModelInfo> {
  return apiFetch<ModelInfo>("/api/model/info");
}

export async function loadModel(checkpoint?: string, device?: string): Promise<ModelInfo> {
  const body = await apiFetch<{ model: ModelInfo }>("/api/model/load", {
    method: "POST",
    body: JSON.stringify({ checkpoint, device }),
  });
  return body.model;
}

export async function signFile(path: string): Promise<string> {
  const params = new URLSearchParams({ path, expires_in: "3600" });
  const body = await apiFetch<{ url: string }>(`/api/file/sign?${params.toString()}`);
  return `${API_BASE}${body.url}`;
}

function boxPayload(box: EditorBox) {
  return { x1: box.x1, y1: box.y1, x2: box.x2, y2: box.y2 };
}

export type PostprocessOptions = {
  minArea: number;
  keepLargest: boolean;
  fillHoles: boolean;
  smoothRadius: number;
};

export const DEFAULT_POSTPROCESS: PostprocessOptions = {
  minArea: 0,
  keepLargest: false,
  fillHoles: false,
  smoothRadius: 0,
};

export async function segmentImage(
  imagePath: string,
  boxes: EditorBox[],
  threshold: number,
  padding = 0,
  postprocess: PostprocessOptions = DEFAULT_POSTPROCESS,
): Promise<SegmentResponse> {
  return apiFetch<SegmentResponse>("/api/segment", {
    method: "POST",
    body: JSON.stringify({
      image_path: imagePath,
      boxes: boxes.map(boxPayload),
      threshold,
      padding,
      postprocess: {
        min_area: postprocess.minArea,
        keep_largest: postprocess.keepLargest,
        fill_holes: postprocess.fillHoles,
        smooth_radius: postprocess.smoothRadius,
      },
    }),
  });
}

export async function getInputPreview(
  imagePath: string,
  box: EditorBox,
  padding = 0,
): Promise<InputPreview> {
  const params = new URLSearchParams({
    image_path: imagePath,
    x1: String(box.x1),
    y1: String(box.y1),
    x2: String(box.x2),
    y2: String(box.y2),
    padding: String(padding),
  });
  return apiFetch<InputPreview>(`/api/model/input-preview?${params.toString()}`);
}

export async function uploadFile(file: File): Promise<string> {
  const params = new URLSearchParams({ name: file.name });
  const body = await apiFetch<{ path: string }>(`/api/upload?${params.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: file,
  });
  return body.path;
}

function chooseFiles(): Promise<File[]> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.multiple = true;
    input.onchange = () => resolve(Array.from(input.files ?? []));
    input.oncancel = () => resolve([]);
    input.click();
  });
}

export async function pickImages(): Promise<string[]> {
  if (bridge?.selectImages) {
    return bridge.selectImages();
  }
  const files = await chooseFiles();
  const paths: string[] = [];
  for (const file of files) {
    paths.push(await uploadFile(file));
  }
  return paths;
}

export function pathFromDrop(file: File): string | null {
  if (bridge?.getPathForFile) {
    try {
      const path = bridge.getPathForFile(file);
      return path || null;
    } catch {
      return null;
    }
  }
  return null;
}

export async function dropFiles(files: File[]): Promise<string[]> {
  const paths: string[] = [];
  for (const file of files) {
    const native = pathFromDrop(file);
    paths.push(native ?? (await uploadFile(file)));
  }
  return paths;
}

export function dataUrl(base64: string): string {
  return `data:image/png;base64,${base64}`;
}

export function absoluteUrl(path?: string | null): string {
  if (!path) return "";
  if (/^https?:\/\//i.test(path) || path.startsWith("data:")) return path;
  return `${API_BASE}${path}`;
}

export async function pickFolder(): Promise<string | null> {
  if (bridge?.selectFolder) return bridge.selectFolder();
  return null;
}

export async function pickAnnotationFile(): Promise<string | null> {
  if (bridge?.selectAnnotationFile) return bridge.selectAnnotationFile();
  return null;
}

export async function parseBatch(
  annotationPath: string,
  annotationFormat: string,
  imageRoot: string,
): Promise<BatchParseResponse> {
  return apiFetch<BatchParseResponse>("/api/batch/parse", {
    method: "POST",
    body: JSON.stringify({
      annotation_path: annotationPath,
      annotation_format: annotationFormat,
      image_root: imageRoot || null,
      preview_limit: 300,
    }),
  });
}

export async function runBatch(
  annotationPath: string,
  annotationFormat: string,
  imageRoot: string,
  options: {
    threshold: number;
    padding: number;
    postprocess: PostprocessOptions;
    labelFilter?: string[];
    skipEmpty: boolean;
    stopOnError: boolean;
  },
): Promise<BatchJob> {
  return apiFetch<BatchJob>("/api/batch/run", {
    method: "POST",
    body: JSON.stringify({
      annotation_path: annotationPath,
      annotation_format: annotationFormat,
      image_root: imageRoot || null,
      threshold: options.threshold,
      padding: options.padding,
      postprocess: {
        min_area: options.postprocess.minArea,
        keep_largest: options.postprocess.keepLargest,
        fill_holes: options.postprocess.fillHoles,
        smooth_radius: options.postprocess.smoothRadius,
      },
      label_filter: options.labelFilter?.length ? options.labelFilter : null,
      skip_empty: options.skipEmpty,
      stop_on_error: options.stopOnError,
    }),
  });
}

export async function getBatchJob(jobId: string, items = true): Promise<BatchJob> {
  return apiFetch<BatchJob>(`/api/batch/jobs/${jobId}?items=${items ? "true" : "false"}`);
}

export async function listBatchJobs(): Promise<BatchJobSummary[]> {
  const body = await apiFetch<{ jobs: BatchJobSummary[] }>("/api/batch/jobs");
  return body.jobs;
}

export async function batchControl(
  jobId: string,
  action: "pause" | "resume" | "cancel" | "retry",
): Promise<BatchJob> {
  return apiFetch<BatchJob>(`/api/batch/jobs/${jobId}/${action}`, { method: "POST" });
}

export async function exportBatch(
  jobId: string,
  destDir: string | null,
  formats: string[],
  naming: string,
): Promise<{
  dest_dir: string;
  formats: string[];
  counts: Record<string, number>;
  coco: string | null;
  csv: string | null;
  labelme_files: number;
}> {
  return apiFetch(`/api/batch/jobs/${jobId}/export`, {
    method: "POST",
    body: JSON.stringify({ dest_dir: destDir, formats, naming }),
  });
}

export async function revealFile(path: string): Promise<void> {
  if (bridge?.revealFile) await bridge.revealFile(path);
}
