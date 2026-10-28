import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Ban,
  CheckCircle2,
  Download,
  FileJson,
  FileText,
  FolderOpen,
  Images,
  Pause,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import {
  absoluteUrl,
  batchControl,
  DEFAULT_POSTPROCESS,
  exportBatch,
  getBatchJob,
  listBatchJobs,
  parseBatch,
  pickAnnotationFile,
  pickFolder,
  runBatch,
  type PostprocessOptions,
} from "../api/client";
import type { BatchJob, BatchJobItem, BatchJobSummary, BatchParseResponse, ModelInfo } from "../types";
import { Modal } from "./Modal";

interface Props {
  model: ModelInfo | null;
  modelError: string | null;
  onOpenSettings(): void;
}

type Step = 1 | 2 | 3;
type Filter = "all" | "done" | "failed" | "skipped";

const FORMAT_OPTIONS = [
  ["auto", "自动检测"],
  ["voc", "Pascal VOC XML"],
  ["coco", "COCO JSON"],
  ["labelme", "LabelMe JSON"],
  ["yolo", "YOLO txt"],
  ["csv", "CSV / 坐标表"],
  ["json", "通用 JSON 坐标"],
] as const;

const STATUS_LABELS: Record<string, string> = {
  pending: "等待中",
  running: "运行中",
  paused: "已暂停",
  interrupted: "已中断",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  done: "成功",
  skipped: "跳过",
};

function statusClass(status: string): string {
  if (status === "done" || status === "completed") return "success";
  if (status === "failed") return "danger";
  if (status === "skipped") return "warn";
  if (status === "running" || status === "paused") return "warn";
  return "";
}

function timeText(value?: number | null): string {
  if (!value) return "—";
  return new Date(value * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function terminal(status: string): boolean {
  return ["completed", "failed", "cancelled"].includes(status);
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="batch-stat">
      <div className="k">{label}</div>
      <div className="v">{value}</div>
    </div>
  );
}

function Check({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange(value: boolean): void;
  label: string;
  hint?: string;
}) {
  return (
    <label className="check-row">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>{label}</span>
      {hint && <span className="check-hint">{hint}</span>}
    </label>
  );
}

export function BatchPage({ model, modelError, onOpenSettings }: Props) {
  const [step, setStep] = useState<Step>(1);
  const [imageRoot, setImageRoot] = useState("");
  const [annotationPath, setAnnotationPath] = useState("");
  const [annotationFormat, setAnnotationFormat] = useState("auto");
  const [preview, setPreview] = useState<BatchParseResponse | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [parsing, setParsing] = useState(false);

  const [threshold, setThreshold] = useState(0.5);
  const [padding, setPadding] = useState(0);
  const [postprocess, setPostprocess] = useState<PostprocessOptions>({ ...DEFAULT_POSTPROCESS });
  const [skipEmpty, setSkipEmpty] = useState(true);
  const [stopOnError, setStopOnError] = useState(false);
  const [labelFilter, setLabelFilter] = useState("");

  const [job, setJob] = useState<BatchJob | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [polling, setPolling] = useState(false);
  const [jobs, setJobs] = useState<BatchJobSummary[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [focusItem, setFocusItem] = useState<BatchJobItem | null>(null);

  const [exportOpen, setExportOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportDest, setExportDest] = useState("");
  const [exportNaming, setExportNaming] = useState("{image}_{box}_{label}");
  const [exportFormats, setExportFormats] = useState<string[]>(["mask", "coco", "csv"]);

  const refreshJobs = useCallback(async () => {
    try {
      setJobs(await listBatchJobs());
    } catch {
      // history is non-critical
    }
  }, []);

  useEffect(() => {
    void refreshJobs();
  }, [refreshJobs]);

  useEffect(() => {
    if (!job || !polling) return;
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const next = await getBatchJob(job.id, true);
        if (cancelled) return;
        setJob(next);
        setJobError(null);
        if (terminal(next.status)) {
          setPolling(false);
          void refreshJobs();
        } else {
          timer = window.setTimeout(tick, 1200);
        }
      } catch (error) {
        if (cancelled) return;
        setJobError(error instanceof Error ? error.message : String(error));
        timer = window.setTimeout(tick, 2200);
      }
    };
    void tick();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [job?.id, polling, refreshJobs]);

  const labels = useMemo(() => {
    const values = new Set<string>();
    for (const record of preview?.records ?? []) {
      for (const box of record.boxes) values.add(box.label || "object");
    }
    return Array.from(values).slice(0, 20);
  }, [preview]);

  const visibleItems = useMemo(() => {
    const items = job?.items ?? [];
    if (filter === "all") return items;
    if (filter === "done") return items.filter((item) => item.status === "done");
    if (filter === "failed") return items.filter((item) => item.status === "failed");
    return items.filter((item) => item.status === "skipped");
  }, [job, filter]);

  const parse = async () => {
    if (!annotationPath.trim()) {
      toast.info("请选择或填写标注路径");
      return;
    }
    setParsing(true);
    setParseError(null);
    try {
      const result = await parseBatch(annotationPath.trim(), annotationFormat, imageRoot.trim());
      setPreview(result);
      toast.success(`解析完成：${result.image_count} 张图 / ${result.box_count} 个框`);
    } catch (error) {
      setPreview(null);
      setParseError(error instanceof Error ? error.message : String(error));
    } finally {
      setParsing(false);
    }
  };

  const start = async () => {
    if (!model?.loaded) {
      toast.error("模型尚未加载");
      return;
    }
    setStarting(true);
    setJobError(null);
    try {
      const filters = labelFilter
        .split(/[,，\s]+/)
        .map((value) => value.trim())
        .filter(Boolean);
      const next = await runBatch(annotationPath.trim(), annotationFormat, imageRoot.trim(), {
        threshold,
        padding,
        postprocess,
        labelFilter: filters,
        skipEmpty,
        stopOnError,
      });
      setJob(next);
      setStep(3);
      setPolling(true);
      setFilter("all");
      void refreshJobs();
      toast.success(`任务已创建：${next.total_images} 张图`);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setJobError(message);
      toast.error(message);
    } finally {
      setStarting(false);
    }
  };

  const control = async (action: "pause" | "resume" | "cancel" | "retry") => {
    if (!job) return;
    try {
      const next = await batchControl(job.id, action);
      setJob(next);
      setJobError(null);
      setPolling(!terminal(next.status) && next.status !== "paused" && next.status !== "interrupted");
      if (action === "resume" || action === "retry") setPolling(true);
      void refreshJobs();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  };

  const openJob = async (summary: BatchJobSummary) => {
    try {
      const full = await getBatchJob(summary.id, true);
      setJob(full);
      setStep(3);
      setFilter("all");
      setPolling(["pending", "running", "paused"].includes(full.status));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  };

  const refreshJob = async () => {
    if (!job) return;
    try {
      const next = await getBatchJob(job.id, true);
      setJob(next);
      setJobError(null);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  };

  const reset = () => {
    setJob(null);
    setStep(1);
    setPolling(false);
    setFilter("all");
    setJobError(null);
  };

  const chooseFolder = async (kind: "images" | "annotations" | "export") => {
    const path = await pickFolder();
    if (!path) {
      toast.info("当前环境不支持原生文件夹选择，可直接粘贴路径");
      return;
    }
    if (kind === "images") setImageRoot(path);
    else if (kind === "annotations") setAnnotationPath(path);
    else setExportDest(path);
  };

  const chooseAnnotationFile = async () => {
    const path = await pickAnnotationFile();
    if (!path) {
      toast.info("当前环境不支持原生文件选择，可直接粘贴路径");
      return;
    }
    setAnnotationPath(path);
  };

  const doExport = async () => {
    if (!job) return;
    setExporting(true);
    try {
      const result = await exportBatch(job.id, exportDest.trim() || null, exportFormats, exportNaming.trim() || "{image}_{box}_{label}");
      toast.success(
        `导出完成：${result.counts.mask} mask / ${result.counts.boxes} 框 → ${result.dest_dir}`,
        { duration: 6000 },
      );
      setExportOpen(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    } finally {
      setExporting(false);
    }
  };

  const progressPercent = Math.round((job?.progress ?? 0) * 100);

  return (
    <div className="batch-workspace">
      <aside className="batch-side">
        <div className="panel-head">
          <span className="panel-title">批量任务</span>
          <span className="panel-count">{jobs.length}</span>
          <span className="spacer" />
          <button className="icon-btn" onClick={reset} title="新建批量任务">
            <Plus size={15} />
          </button>
        </div>
        <div className="panel-scroll">
          {jobs.length === 0 ? (
            <div className="empty-note">
              还没有批量任务。
              <br />
              从右侧导入图片和标注开始。
            </div>
          ) : (
            <div className="job-history">
              {jobs.map((summary) => (
                <button
                  key={summary.id}
                  className={`job-history-item ${job?.id === summary.id ? "active" : ""}`}
                  onClick={() => void openJob(summary)}
                >
                  <span className={`status-dot ${summary.status === "completed" ? "done" : summary.status === "failed" ? "error" : ""}`} />
                  <span className="job-history-meta">
                    <span className="job-history-title">
                      {summary.total_images} 图 · {summary.total_boxes} 框
                    </span>
                    <span className="job-history-sub">
                      {timeText(summary.created_at)} · {STATUS_LABELS[summary.status] ?? summary.status}
                    </span>
                  </span>
                  <span className="job-history-progress">{Math.round(summary.progress * 100)}%</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="batch-side-model">
          <div className="kv">
            <span>模型</span>
            <span className="v">{model?.loaded ? model.device?.toUpperCase() : "未加载"}</span>
          </div>
          <div className="kv">
            <span>输入</span>
            <span className="v">6 × 512 × 768</span>
          </div>
          {!model?.loaded && (
            <button className="btn btn-block btn-sm" onClick={onOpenSettings}>
              加载模型
            </button>
          )}
        </div>
      </aside>

      <main className="batch-main">
        <header className="batch-page-head">
          <div>
            <h1>批量框选分割</h1>
            <p>导入图片与现成框标注，批量生成 mask 并导出 COCO / LabelMe / CSV。</p>
          </div>
          {!model?.loaded && (
            <div className="warning-note batch-model-warning">
              {modelError ?? "模型尚未加载，批量处理会被禁用。"}
              <button className="btn btn-sm" onClick={onOpenSettings}>
                去设置
              </button>
            </div>
          )}
        </header>

        <div className="batch-stepper">
          {[
            [1, "导入与配对"],
            [2, "参数"],
            [3, "运行与结果"],
          ].map(([value, title]) => (
            <button
              key={String(value)}
              className={`batch-step ${step === value ? "active" : ""} ${step > Number(value) ? "done" : ""}`}
              onClick={() => setStep(value as Step)}
            >
              <span className="batch-step-index">{step > Number(value) ? <CheckCircle2 size={13} /> : value}</span>
              <span>{title}</span>
            </button>
          ))}
        </div>

        {step === 1 && (
          <section className="batch-card">
            <div className="batch-card-head">
              <div>
                <h2>① 导入图片与标注</h2>
                <p>支持 VOC / COCO / LabelMe / YOLO / CSV，自动配对；空标注会标记为跳过。</p>
              </div>
              <button className="btn" onClick={() => void parse()} disabled={parsing}>
                {parsing ? <span className="spinner" /> : <RefreshCw size={13} />}
                解析并预览
              </button>
            </div>

            <div className="source-grid">
              <div className="source-card">
                <div className="source-label">
                  <Images size={14} />
                  图片文件夹
                </div>
                <div className="path-row">
                  <input
                    className="input"
                    value={imageRoot}
                    onChange={(event) => setImageRoot(event.target.value)}
                    placeholder="例如 D:\dataset\JPEGImages"
                    spellCheck={false}
                  />
                  <button className="btn" onClick={() => void chooseFolder("images")}>
                    <FolderOpen size={13} />
                    选择
                  </button>
                </div>
                <div className="source-hint">批量推理会按标注中的图片名在此目录递归查找。</div>
              </div>

              <div className="source-card">
                <div className="source-label">
                  <FileJson size={14} />
                  标注文件 / 文件夹
                </div>
                <div className="path-row">
                  <input
                    className="input"
                    value={annotationPath}
                    onChange={(event) => setAnnotationPath(event.target.value)}
                    placeholder="Annotations 文件夹，或 instances.json / manifest.csv"
                    spellCheck={false}
                  />
                  <button className="btn" onClick={() => void chooseFolder("annotations")}>
                    <FolderOpen size={13} />
                    文件夹
                  </button>
                  <button className="btn" onClick={() => void chooseAnnotationFile()}>
                    <FileText size={13} />
                    文件
                  </button>
                </div>
                <div className="path-row" style={{ marginTop: 7 }}>
                  <select
                    className="input"
                    style={{ fontFamily: "var(--font-sans)" }}
                    value={annotationFormat}
                    onChange={(event) => setAnnotationFormat(event.target.value)}
                  >
                    {FORMAT_OPTIONS.map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                  <span className="source-hint" style={{ flex: 1 }}>
                    {labels.length ? `检测到类别：${labels.join(" / ")}` : "自动检测失败时可手动指定格式。"}
                  </span>
                </div>
              </div>
            </div>

            {parseError && <div className="warning-note">{parseError}</div>}

            {preview && (
              <>
                <div className="batch-summary">
                  <StatCard label="图片" value={preview.image_count} />
                  <StatCard label="框" value={preview.box_count} />
                  <StatCard label="缺图片" value={preview.missing_images} />
                  <StatCard label="空标注" value={preview.empty_images} />
                  <div className="batch-summary-format">
                    <span className="badge success">{preview.format.toUpperCase()}</span>
                    {preview.truncated && <span className="badge warn">预览仅前 300 行</span>}
                  </div>
                </div>
                {preview.warnings.length > 0 && (
                  <div className="warning-list">
                    {preview.warnings.slice(0, 8).map((warning, index) => (
                      <div key={`${index}-${warning}`} className="warning-line">
                        <AlertTriangle size={12} />
                        {warning}
                      </div>
                    ))}
                  </div>
                )}
                <div className="batch-table">
                  <div className="batch-table-head">
                    <span>图片</span>
                    <span>框数</span>
                    <span>类别</span>
                    <span>状态</span>
                  </div>
                  <div className="batch-table-body">
                    {preview.records.map((record, index) => {
                      const recordLabels = Array.from(new Set(record.boxes.map((box) => box.label || "object")));
                      const state = !record.image_path
                        ? "缺图片"
                        : record.boxes.length === 0
                          ? "空标注"
                          : "已配对";
                      return (
                        <div className="batch-table-row" key={`${index}-${record.image_path}-${record.name}`}>
                          <span className="batch-file-name" title={record.image_path ?? record.name}>
                            {record.name}
                          </span>
                          <span className="mono">{record.boxes.length}</span>
                          <span className="batch-labels">{recordLabels.join(", ") || "—"}</span>
                          <span className={`badge ${state === "已配对" ? "success" : state === "空标注" ? "warn" : "danger"}`}>
                            {state}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </>
            )}

            <div className="batch-footer">
              <span className="hint">
                先解析确认配对和框数量；解析只读取标注，不会修改文件。
              </span>
              <button
                className="btn btn-primary"
                disabled={!preview || starting}
                onClick={() => setStep(2)}
              >
                下一步：参数
                <ArrowRight size={13} />
              </button>
            </div>
          </section>
        )}

        {step === 2 && (
          <section className="batch-card">
            <div className="batch-card-head">
              <div>
                <h2>② 分割参数</h2>
                <p>默认与训练一致（阈值 0.5、无后处理）；批量任务使用同一套参数。</p>
              </div>
              <span className="badge success">已解析 {preview?.image_count ?? 0} 图</span>
            </div>

            <div className="batch-param-grid">
              <div className="field">
                <label>阈值</label>
                <div className="slider-row">
                  <input
                    type="range"
                    min={0.05}
                    max={0.95}
                    step={0.01}
                    value={threshold}
                    onChange={(event) => setThreshold(Number(event.target.value))}
                  />
                  <span className="slider-value">{threshold.toFixed(2)}</span>
                </div>
              </div>
              <div className="field">
                <label>框外扩 padding (px)</label>
                <input
                  className="input"
                  type="number"
                  min={0}
                  max={512}
                  value={padding}
                  onChange={(event) => setPadding(Math.max(0, Math.min(512, Number(event.target.value) || 0)))}
                />
              </div>
              <div className="field">
                <label>最小面积 (px)</label>
                <input
                  className="input"
                  type="number"
                  min={0}
                  value={postprocess.minArea}
                  disabled={postprocess.keepLargest}
                  onChange={(event) =>
                    setPostprocess((current) => ({ ...current, minArea: Number(event.target.value) || 0 }))
                  }
                />
              </div>
              <div className="field">
                <label>平滑半径 (px)</label>
                <input
                  className="input"
                  type="number"
                  min={0}
                  max={32}
                  value={postprocess.smoothRadius}
                  onChange={(event) =>
                    setPostprocess((current) => ({
                      ...current,
                      smoothRadius: Math.max(0, Math.min(32, Number(event.target.value) || 0)),
                    }))
                  }
                />
              </div>
            </div>

            <div className="batch-checks">
              <Check
                checked={postprocess.keepLargest}
                onChange={(value) => setPostprocess((current) => ({ ...current, keepLargest: value }))}
                label="仅保留最大连通域"
              />
              <Check
                checked={postprocess.fillHoles}
                onChange={(value) => setPostprocess((current) => ({ ...current, fillHoles: value }))}
                label="填充内部空洞"
              />
              <Check checked={skipEmpty} onChange={setSkipEmpty} label="跳过无框图" />
              <Check checked={stopOnError} onChange={setStopOnError} label="遇错停止任务" />
            </div>

            <div className="field">
              <label>只处理这些类别（可选，逗号分隔）</label>
              <input
                className="input"
                style={{ fontFamily: "var(--font-sans)" }}
                value={labelFilter}
                onChange={(event) => setLabelFilter(event.target.value)}
                placeholder={labels.length ? `例如 ${labels.slice(0, 3).join(",")}` : "留空处理全部类别"}
              />
              <div className="hint">
                模型本身是二分类前景分割，label 只用于过滤、命名和导出，不影响框内 mask。
              </div>
            </div>

            <div className="batch-footer">
              <button className="btn" onClick={() => setStep(1)}>
                <ArrowLeft size={13} />
                返回
              </button>
              <button className="btn btn-primary" onClick={() => void start()} disabled={starting || !model?.loaded}>
                {starting ? <span className="spinner" /> : <Play size={13} />}
                开始批量处理
              </button>
            </div>
          </section>
        )}

        {step === 3 && (
          <>
            {!job ? (
              <section className="batch-card">
                <div className="batch-empty">
                  <SparkEmpty onBack={reset} />
                </div>
              </section>
            ) : (
              <>
                <section className="batch-card">
                  <div className="batch-progress-head">
                    <div>
                      <h2>
                        任务 {job.id}
                        <span className={`badge ${statusClass(job.status)}`} style={{ marginLeft: 8 }}>
                          {STATUS_LABELS[job.status] ?? job.status}
                        </span>
                      </h2>
                      <p>
                        {job.done_images} / {job.total_images} 图 · {job.done_boxes} / {job.total_boxes} 框
                        {job.current_name ? ` · 当前：${job.current_name}` : ""}
                      </p>
                    </div>
                    <div className="batch-actions">
                      {job.status === "running" && (
                        <button className="btn" onClick={() => void control("pause")}>
                          <Pause size={13} />
                          暂停
                        </button>
                      )}
                      {(job.status === "paused" || job.status === "interrupted") && (
                        <button className="btn btn-primary" onClick={() => void control("resume")}>
                          <Play size={13} />
                          继续
                        </button>
                      )}
                      {["running", "paused", "interrupted", "pending"].includes(job.status) && (
                        <button className="btn btn-danger" onClick={() => void control("cancel")}>
                          <Ban size={13} />
                          取消
                        </button>
                      )}
                      {job.failed_images > 0 && (
                        <button className="btn" onClick={() => void control("retry")}>
                          <RotateCcw size={13} />
                          重试失败
                        </button>
                      )}
                      <button
                        className="btn btn-primary"
                        onClick={() => setExportOpen(true)}
                        disabled={job.done_images === 0}
                      >
                        <Download size={13} />
                        导出
                      </button>
                      <button className="btn" onClick={() => void refreshJob()} title="刷新状态">
                        <RefreshCw size={13} />
                      </button>
                    </div>
                  </div>

                  <div className="batch-progress">
                    <div className="batch-progress-bar">
                      <div className="batch-progress-fill" style={{ width: `${progressPercent}%` }} />
                    </div>
                    <span className="batch-progress-text">{progressPercent}%</span>
                  </div>

                  <div className="batch-summary four">
                    <StatCard label="成功" value={job.done_images} />
                    <StatCard label="失败" value={job.failed_images} />
                    <StatCard label="跳过" value={job.skipped_images} />
                    <StatCard label="框" value={job.done_boxes} />
                  </div>
                  {job.error && <div className="warning-note">{job.error}</div>}
                  {jobError && <div className="warning-note">{jobError}</div>}
                </section>

                <section className="batch-card">
                  <div className="batch-card-head">
                    <div>
                      <h2>结果</h2>
                      <p>点击卡片查看 mask 叠加；失败/跳过项保留原因，便于修正后重跑。</p>
                    </div>
                    <div className="batch-actions">
                      <button className={`chip ${filter === "all" ? "active" : ""}`} onClick={() => setFilter("all")}>
                        全部 {job.items?.length ?? 0}
                      </button>
                      <button className={`chip ${filter === "done" ? "active" : ""}`} onClick={() => setFilter("done")}>
                        成功 {job.done_images}
                      </button>
                      <button className={`chip ${filter === "failed" ? "active" : ""}`} onClick={() => setFilter("failed")}>
                        失败 {job.failed_images}
                      </button>
                      <button className={`chip ${filter === "skipped" ? "active" : ""}`} onClick={() => setFilter("skipped")}>
                        跳过 {job.skipped_images}
                      </button>
                    </div>
                  </div>

                  {visibleItems.length === 0 ? (
                    <div className="empty-note">当前筛选下没有结果。</div>
                  ) : (
                    <div className="batch-result-grid">
                      {visibleItems.map((item) => {
                        const first = item.results[0];
                        return (
                          <button
                            className="batch-result-card"
                            key={item.index}
                            onClick={() => setFocusItem(item)}
                            title={item.image_path ?? item.name}
                          >
                            <span className="batch-result-thumb">
                              {first?.overlay_url ? (
                                <img src={absoluteUrl(first.overlay_url)} alt="" loading="lazy" />
                              ) : (
                                <span className="batch-result-placeholder">
                                  {item.status === "failed" ? <XCircle size={18} /> : <AlertTriangle size={18} />}
                                </span>
                              )}
                              <span className={`batch-result-status ${statusClass(item.status)}`}>
                                {STATUS_LABELS[item.status] ?? item.status}
                              </span>
                            </span>
                            <span className="batch-result-meta">
                              <span className="batch-result-name">{item.name}</span>
                              <span className="batch-result-sub">
                                {item.results.length} mask
                                {item.elapsed_ms ? ` · ${Math.round(item.elapsed_ms)} ms` : ""}
                              </span>
                              {item.error && <span className="batch-result-error">{item.error}</span>}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </section>
              </>
            )}
          </>
        )}
      </main>

      {focusItem && (
        <Modal
          title={focusItem.name}
          icon={<Images size={15} />}
          wide
          onClose={() => setFocusItem(null)}
          footer={
            <button className="btn" onClick={() => setFocusItem(null)}>
              关闭
            </button>
          }
        >
          {focusItem.status !== "done" ? (
            <div className="warning-note">
              {STATUS_LABELS[focusItem.status] ?? focusItem.status}
              {focusItem.error ? `：${focusItem.error}` : ""}
            </div>
          ) : (
            <>
              <div className="batch-result-detail">
                {focusItem.results.map((result) => (
                  <div className="batch-result-detail-item" key={result.box_index}>
                    <img src={absoluteUrl(result.overlay_url)} alt="" />
                    <div className="batch-result-detail-meta">
                      <span>
                        框 {result.box_index + 1} · {result.label}
                      </span>
                      <span>
                        {result.area_px.toLocaleString()} px · {(result.area_ratio * 100).toFixed(2)}% ·{" "}
                        {Math.round(result.latency_ms)} ms
                      </span>
                      {result.warning && <span className="warning-note">{result.warning}</span>}
                    </div>
                  </div>
                ))}
              </div>
              <div className="kv">
                <span>图片路径</span>
                <span className="v" title={focusItem.image_path ?? ""}>
                  {focusItem.image_path ?? "—"}
                </span>
              </div>
            </>
          )}
        </Modal>
      )}

      {exportOpen && job && (
        <Modal
          title="导出批量结果"
          icon={<Download size={15} />}
          onClose={() => setExportOpen(false)}
          footer={
            <>
              <button className="btn" onClick={() => setExportOpen(false)}>
                取消
              </button>
              <button className="btn btn-primary" onClick={() => void doExport()} disabled={exporting || !exportFormats.length}>
                {exporting ? <span className="spinner" /> : <Download size={13} />}
                开始导出
              </button>
            </>
          }
        >
          <div className="field">
            <label>导出目录</label>
            <div className="path-row">
              <input
                className="input"
                value={exportDest}
                onChange={(event) => setExportDest(event.target.value)}
                placeholder="留空则导出到任务目录下的 export/"
                spellCheck={false}
              />
              <button className="btn" onClick={() => void chooseFolder("export")}>
                <FolderOpen size={13} />
                选择
              </button>
            </div>
          </div>
          <div className="field">
            <label>格式（可多选）</label>
            <div className="batch-checks">
              {[
                ["mask", "mask PNG"],
                ["overlay", "叠加图 PNG"],
                ["coco", "COCO 实例分割 JSON"],
                ["labelme", "LabelMe polygon JSON"],
                ["csv", "结果 CSV"],
              ].map(([value, label]) => (
                <Check
                  key={value}
                  checked={exportFormats.includes(value)}
                  onChange={(checked) =>
                    setExportFormats((current) =>
                      checked ? [...current, value] : current.filter((item) => item !== value),
                    )
                  }
                  label={label}
                />
              ))}
            </div>
          </div>
          <div className="field">
            <label>命名模板</label>
            <input
              className="input"
              value={exportNaming}
              onChange={(event) => setExportNaming(event.target.value)}
              spellCheck={false}
            />
            <div className="hint">可用占位符：{"{image} {index} {box} {label}"}；冲突时自动加序号。</div>
          </div>
          {job.done_images === 0 && <div className="warning-note">任务还没有成功结果。</div>}
        </Modal>
      )}
    </div>
  );
}

function SparkEmpty({ onBack }: { onBack(): void }) {
  return (
    <>
      <FileText size={26} />
      <h3>还没有选中批量任务</h3>
      <p>从左侧选择一个历史任务，或新建批量任务。</p>
      <button className="btn btn-primary" onClick={onBack}>
        <Plus size={13} />
        新建批量任务
      </button>
    </>
  );
}
