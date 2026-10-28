import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent as ReactDragEvent,
} from "react";
import { ImagePlus } from "lucide-react";
import { Toaster, toast } from "sonner";
import { BatchPage } from "./components/BatchPage";
import { CanvasStage } from "./components/CanvasStage";
import { HelpDialog } from "./components/HelpDialog";
import { ImageList } from "./components/ImageList";
import { Inspector } from "./components/Inspector";
import { PreviewDialog } from "./components/PreviewDialog";
import { SettingsDialog } from "./components/SettingsDialog";
import { TopBar } from "./components/TopBar";
import { useImageElement } from "./hooks/useImageElement";
import {
  dropFiles,
  getHealth,
  getInputPreview,
  loadModel,
  pickImages,
  segmentImage,
  signFile,
} from "./api/client";
import { useEditor } from "./store/editor";
import type {
  EditorBox,
  EditorImage,
  InputPreview,
  ModelInfo,
  SegmentResult,
} from "./types";

const EMPTY_BOXES: EditorBox[] = [];
const EMPTY_RESULTS: Record<string, SegmentResult> = {};
const IMAGE_EXT = /\.(jpe?g|png|bmp|webp|tiff?)$/i;

async function collectDropFiles(dataTransfer: DataTransfer): Promise<File[]> {
  const items = Array.from(dataTransfer.items);
  const entries = items
    .map((item) =>
      (item as DataTransferItem & {
        webkitGetAsEntry?: () => FileSystemEntry | null;
      }).webkitGetAsEntry?.(),
    )
    .filter((entry): entry is FileSystemEntry => Boolean(entry));

  if (!entries.length) return Array.from(dataTransfer.files);

  const files: File[] = [];
  const walk = async (entry: FileSystemEntry): Promise<void> => {
    if (entry.isFile) {
      const file = await new Promise<File>((resolve, reject) => {
        (entry as FileSystemFileEntry).file(resolve, reject);
      });
      if (IMAGE_EXT.test(file.name)) files.push(file);
      return;
    }
    if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      for (;;) {
        const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => {
          reader.readEntries(resolve, reject);
        });
        if (!batch.length) break;
        for (const child of batch) await walk(child);
      }
    }
  };
  for (const entry of entries) await walk(entry);
  return files;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export default function App() {
  const images = useEditor((state) => state.images);
  const currentId = useEditor((state) => state.currentId);
  const boxesByImage = useEditor((state) => state.boxesByImage);
  const resultsByImage = useEditor((state) => state.resultsByImage);
  const selectedBoxId = useEditor((state) => state.selectedBoxId);
  const threshold = useEditor((state) => state.threshold);
  const padding = useEditor((state) => state.padding);
  const postprocess = useEditor((state) => state.postprocess);
  const autoRun = useEditor((state) => state.autoRun);
  const busy = useEditor((state) => state.busy);
  const tool = useEditor((state) => state.tool);
  const showMask = useEditor((state) => state.showMask);
  const maskOpacity = useEditor((state) => state.maskOpacity);
  const viewMode = useEditor((state) => state.viewMode);
  const past = useEditor((state) => state.past);
  const future = useEditor((state) => state.future);

  const addPaths = useEditor((state) => state.addPaths);
  const updateImage = useEditor((state) => state.updateImage);
  const removeImage = useEditor((state) => state.removeImage);
  const setCurrent = useEditor((state) => state.setCurrent);
  const addBox = useEditor((state) => state.addBox);
  const updateBox = useEditor((state) => state.updateBox);
  const updateBoxMeta = useEditor((state) => state.updateBoxMeta);
  const removeBox = useEditor((state) => state.removeBox);
  const selectBox = useEditor((state) => state.selectBox);
  const setResultForImage = useEditor((state) => state.setResultForImage);
  const setThreshold = useEditor((state) => state.setThreshold);
  const setPadding = useEditor((state) => state.setPadding);
  const setPostprocess = useEditor((state) => state.setPostprocess);
  const setAutoRun = useEditor((state) => state.setAutoRun);
  const setBusy = useEditor((state) => state.setBusy);
  const setTool = useEditor((state) => state.setTool);
  const setShowMask = useEditor((state) => state.setShowMask);
  const setMaskOpacity = useEditor((state) => state.setMaskOpacity);
  const setViewMode = useEditor((state) => state.setViewMode);
  const undo = useEditor((state) => state.undo);
  const redo = useEditor((state) => state.redo);

  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = window.localStorage.getItem("boxmask.theme");
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  const [mode, setMode] = useState<"single" | "batch">("single");
  const [model, setModel] = useState<ModelInfo | null>(null);
  const [modelError, setModelError] = useState<string | null>(null);
  const [loadingModel, setLoadingModel] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [cursor, setCursor] = useState<{ x: number | null; y: number | null }>({
    x: null,
    y: null,
  });
  const [preview, setPreview] = useState<InputPreview | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const dragDepth = useRef(0);
  const lastCursor = useRef(0);
  const runSeq = useRef(0);
  const autoTimer = useRef<number | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("boxmask.theme", theme);
  }, [theme]);

  useEffect(() => {
    return () => {
      if (autoTimer.current) window.clearTimeout(autoTimer.current);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let attempts = 0;
    const tick = async () => {
      try {
        const health = await getHealth();
        if (cancelled) return;
        setModel(health.model);
        setModelError(null);
      } catch (error) {
        if (cancelled) return;
        setModelError(errorMessage(error));
        if (attempts < 12) {
          attempts += 1;
          window.setTimeout(tick, 1500);
        }
      }
    };
    void tick();
    return () => {
      cancelled = true;
    };
  }, []);

  const currentImage = useMemo(
    () => images.find((image) => image.id === currentId),
    [images, currentId],
  );
  const currentBoxes = currentId ? boxesByImage[currentId] ?? EMPTY_BOXES : EMPTY_BOXES;
  const currentResults = currentId ? resultsByImage[currentId] ?? EMPTY_RESULTS : EMPTY_RESULTS;
  const selectedBox = currentBoxes.find((box) => box.id === selectedBoxId) ?? null;
  const { image: imageElement, error: imageElementError } = useImageElement(currentImage?.url);

  const imageWidth = currentImage?.width ?? imageElement?.naturalWidth ?? 0;
  const imageHeight = currentImage?.height ?? imageElement?.naturalHeight ?? 0;

  const resultCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const [imageId, results] of Object.entries(resultsByImage)) {
      counts[imageId] = Object.keys(results).length;
    }
    return counts;
  }, [resultsByImage]);

  const hydrateImage = useCallback(
    async (image: EditorImage) => {
      try {
        const url = await signFile(image.path);
        const meta = await new Promise<{ width: number; height: number }>((resolve, reject) => {
          const element = new Image();
          element.onload = () =>
            resolve({ width: element.naturalWidth, height: element.naturalHeight });
          element.onerror = () => reject(new Error("图片解码失败"));
          element.src = url;
        });
        updateImage(image.id, {
          url,
          width: meta.width,
          height: meta.height,
          status: "ready",
        });
      } catch (error) {
        updateImage(image.id, { status: "error" });
        toast.error(`无法打开 ${image.name}：${errorMessage(error)}`);
      }
    },
    [updateImage],
  );

  const hydrateOnce = useRef(false);
  useEffect(() => {
    if (hydrateOnce.current) return;
    hydrateOnce.current = true;
    const pending = useEditor.getState().images.filter((image) => !image.url);
    for (const image of pending) void hydrateImage(image);
  }, [hydrateImage]);

  const importPaths = useCallback(
    async (paths: string[]) => {
      if (!paths.length) return;
      const before = new Set(useEditor.getState().images.map((image) => image.path));
      addPaths(paths);
      const fresh = useEditor
        .getState()
        .images.filter((image) => !before.has(image.path));
      if (!fresh.length) return;
      await Promise.all(fresh.map(hydrateImage));
      toast.success(`已导入 ${fresh.length} 张图片`);
    },
    [addPaths, hydrateImage],
  );

  const handleImport = useCallback(async () => {
    try {
      const paths = await pickImages();
      await importPaths(paths);
    } catch (error) {
      toast.error(`导入失败：${errorMessage(error)}`);
    }
  }, [importPaths]);

  const handleDrop = useCallback(
    async (event: ReactDragEvent) => {
      event.preventDefault();
      dragDepth.current = 0;
      setDragOver(false);
      if (mode !== "single") {
        toast.info("批量模式请在批量页选择图片文件夹与标注路径");
        return;
      }
      try {
        const files = await collectDropFiles(event.dataTransfer);
        if (!files.length) {
          toast.info("没有找到可导入的图片");
          return;
        }
        const paths = await dropFiles(files);
        await importPaths(paths);
      } catch (error) {
        toast.error(`导入失败：${errorMessage(error)}`);
      }
    },
    [importPaths, mode],
  );

  const runBoxes = useCallback(
    async (image: EditorImage, boxesToRun: EditorBox[], mode: "auto" | "manual" = "manual") => {
      if (!boxesToRun.length) return;
      if (!model?.loaded) {
        if (mode === "manual") toast.error("模型尚未加载，请先在设置中加载 checkpoint。");
        return;
      }
      if (useEditor.getState().busy) {
        if (mode === "manual") toast.info("正在处理上一个请求，请稍候。");
        return;
      }
      const seq = ++runSeq.current;
      setBusy(true);
      try {
        const response = await segmentImage(
          image.path,
          boxesToRun,
          threshold,
          padding,
          postprocess,
        );
        if (seq !== runSeq.current) return;
        response.results.forEach((item, index) => {
          const box = boxesToRun[index];
          if (!box) return;
          setResultForImage(image.id, box.id, {
            boxId: box.id,
            maskBase64: item.mask_png_base64,
            overlayBase64: item.overlay_png_base64 ?? undefined,
            areaPx: item.area_px,
            areaRatio: item.area_ratio,
            meanProb: item.mean_prob ?? undefined,
            latencyMs: item.latency_ms,
            warning: item.warning ?? undefined,
            boxUsed: item.box_used,
            fallbackFullImage: item.fallback_full_image,
          });
        });
        updateImage(image.id, { width: response.width, height: response.height });
      } catch (error) {
        if (seq === runSeq.current && mode === "manual") {
          toast.error(`分割失败：${errorMessage(error)}`);
        }
      } finally {
        if (seq === runSeq.current) setBusy(false);
      }
    },
    [model?.loaded, threshold, padding, postprocess, setResultForImage, setBusy, updateImage],
  );

  const handleCreateBox = useCallback(
    (box: EditorBox) => {
      addBox(box);
      if (autoRun && currentImage) {
        void runBoxes(currentImage, [box], "auto");
      }
    },
    [addBox, autoRun, currentImage, runBoxes],
  );

  const handleChangeBox = useCallback(
    (id: string, patch: Partial<EditorBox>) => {
      updateBox(id, patch);
      if (!autoRun) return;
      if (autoTimer.current) window.clearTimeout(autoTimer.current);
      autoTimer.current = window.setTimeout(() => {
        const state = useEditor.getState();
        if (state.busy || !state.currentId) return;
        const image = state.images.find((item) => item.id === state.currentId);
        const box = (state.boxesByImage[state.currentId] ?? []).find((item) => item.id === id);
        if (image && box) void runBoxes(image, [box], "auto");
      }, 320);
    },
    [updateBox, autoRun, runBoxes],
  );

  const runSelected = useCallback(() => {
    if (selectedBox && currentImage) {
      void runBoxes(currentImage, [selectedBox], "manual");
    } else {
      toast.info("先在画布上选择一个框");
    }
  }, [selectedBox, currentImage, runBoxes]);

  const runAll = useCallback(() => {
    if (currentImage && currentBoxes.length) {
      void runBoxes(currentImage, currentBoxes, "manual");
    }
  }, [currentImage, currentBoxes, runBoxes]);

  const navigateImage = useCallback(
    (delta: number) => {
      if (!images.length) return;
      const index = currentId ? images.findIndex((image) => image.id === currentId) : -1;
      const next = images[Math.max(0, Math.min(images.length - 1, index + delta))];
      if (next && next.id !== currentId) setCurrent(next.id);
    },
    [images, currentId, setCurrent],
  );

  const handleCursor = useCallback((x: number | null, y: number | null) => {
    const now = performance.now();
    if (now - lastCursor.current < 70) return;
    lastCursor.current = now;
    setCursor({ x, y });
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (showSettings || showHelp || previewOpen || mode === "batch") return;
      const target = event.target as HTMLElement | null;
      if (target && (/input|textarea|select/i.test(target.tagName) || target.isContentEditable)) {
        return;
      }
      const key = event.key.toLowerCase();
      if (!event.ctrlKey && !event.metaKey && !event.altKey) {
        if (key === "v") {
          setTool("select");
          return;
        }
        if (key === "b") {
          setTool("draw");
          return;
        }
        if (key === "h") {
          setTool("pan");
          return;
        }
        if (key === "escape") {
          setTool("select");
          selectBox(null);
          return;
        }
        if (key === "enter") {
          event.preventDefault();
          runSelected();
          return;
        }
        if ((event.key === "Delete" || event.key === "Backspace") && selectedBox) {
          event.preventDefault();
          removeBox(selectedBox.id);
          return;
        }
      }
      if ((event.ctrlKey || event.metaKey) && key === "z") {
        event.preventDefault();
        if (event.shiftKey) redo();
        else undo();
        return;
      }
      if ((event.ctrlKey || event.metaKey) && key === "y") {
        event.preventDefault();
        redo();
        return;
      }
      if (event.altKey && event.key === "ArrowLeft") {
        event.preventDefault();
        navigateImage(-1);
        return;
      }
      if (event.altKey && event.key === "ArrowRight") {
        event.preventDefault();
        navigateImage(1);
        return;
      }
      if ((event.ctrlKey || event.metaKey) && key === "o") {
        event.preventDefault();
        void handleImport();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    setTool,
    selectBox,
    runSelected,
    selectedBox,
    removeBox,
    navigateImage,
    handleImport,
    showSettings,
    showHelp,
    previewOpen,
    mode,
    undo,
    redo,
  ]);

  useEffect(() => {
    if (!import.meta.env.DEV) return;
    const debugWindow = window as typeof window & {
      __boxmaskImportPaths?: (paths: string[]) => Promise<void>;
      __boxmaskAddBox?: (box: EditorBox) => void;
      __boxmaskState?: () => ReturnType<typeof useEditor.getState>;
    };
    debugWindow.__boxmaskImportPaths = importPaths;
    debugWindow.__boxmaskAddBox = handleCreateBox;
    debugWindow.__boxmaskState = () => useEditor.getState();
  }, [importPaths, handleCreateBox]);

  const handlePreview = useCallback(
    async (box: EditorBox) => {
      if (!currentImage) return;
      setPreviewOpen(true);
      setPreview(null);
      setPreviewError(null);
      setPreviewLoading(true);
      try {
        const data = await getInputPreview(currentImage.path, box, padding);
        setPreview(data);
      } catch (error) {
        setPreviewError(errorMessage(error));
      } finally {
        setPreviewLoading(false);
      }
    },
    [currentImage, padding],
  );

  const handleLoadModel = useCallback(
    async (checkpoint?: string, device?: string) => {
      setLoadingModel(true);
      setModelError(null);
      try {
        const info = await loadModel(checkpoint, device);
        setModel(info);
        toast.success("模型已加载");
      } catch (error) {
        const message = errorMessage(error);
        setModelError(message);
        throw error;
      } finally {
        setLoadingModel(false);
      }
    },
    [],
  );

  const lastResult =
    (selectedBox ? currentResults[selectedBox.id] : undefined) ??
    Object.values(currentResults).slice(-1)[0];
  const statusText = busy
    ? "推理中"
    : model?.loaded
      ? `${model.device?.toUpperCase() ?? "CPU"} · 就绪`
      : "模型未加载";

  return (
    <div
      className="app-shell"
      onDragEnter={(event) => {
        if (mode !== "single") return;
        event.preventDefault();
        dragDepth.current += 1;
        setDragOver(true);
      }}
      onDragOver={(event) => {
        if (mode !== "single") return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
      }}
      onDragLeave={(event) => {
        if (mode !== "single") return;
        event.preventDefault();
        dragDepth.current -= 1;
        if (dragDepth.current <= 0) {
          dragDepth.current = 0;
          setDragOver(false);
        }
      }}
      onDrop={handleDrop}
    >
      <TopBar
        model={model}
        modelError={modelError}
        loadingModel={loadingModel}
        theme={theme}
        mode={mode}
        onModeChange={setMode}
        onThemeChange={setTheme}
        onSettings={() => setShowSettings(true)}
        onHelp={() => setShowHelp(true)}
      />

      <div className={mode === "single" ? "workspace" : "batch-host"}>
        {mode === "single" ? (
          <>
        <aside className="sidebar">
          <ImageList
            images={images}
            currentId={currentId}
            resultCounts={resultCounts}
            onSelect={setCurrent}
            onRemove={removeImage}
            onImport={handleImport}
          />
        </aside>

        <main className="canvas-pane">
          {!currentImage ? (
            <div className="canvas-empty">
              <div className={`dropzone ${dragOver ? "drag-over" : ""}`}>
                <div className="dropzone-icon">
                  <ImagePlus size={22} />
                </div>
                <h2>导入图片开始框选分割</h2>
                <p>
                  拖拽图片或文件夹到这里，或点击选择图片。
                  <br />
                  JPG / PNG / BMP / WEBP / TIFF · 支持中文路径
                </p>
                <button className="btn btn-primary" onClick={handleImport}>
                  <ImagePlus size={14} />
                  选择图片
                </button>
              </div>
            </div>
          ) : !imageElement || imageWidth === 0 ? (
            <div className="canvas-empty">
              <div className="dropzone">
                {currentImage.status === "error" || imageElementError ? (
                  <>
                    <h2>图片加载失败</h2>
                    <p>{imageElementError ?? "请移除这张图片后重新导入。"}</p>
                    <button className="btn" onClick={() => removeImage(currentImage.id)}>
                      移除图片
                    </button>
                  </>
                ) : (
                  <>
                    <span className="spinner" style={{ color: "var(--mask)", width: 20, height: 20 }} />
                    <p>正在加载图片…</p>
                  </>
                )}
              </div>
            </div>
          ) : (
            <CanvasStage
              image={imageElement}
              imageWidth={imageWidth}
              imageHeight={imageHeight}
              boxes={currentBoxes}
              selectedBoxId={selectedBoxId}
              results={currentResults}
              tool={tool}
              viewMode={viewMode}
              showMask={showMask}
              maskOpacity={maskOpacity}
              canUndo={past.length > 0}
              canRedo={future.length > 0}
              onUndo={undo}
              onRedo={redo}
              onToolChange={setTool}
              onSelectBox={selectBox}
              onCreateBox={handleCreateBox}
              onChangeBox={handleChangeBox}
              onCursor={handleCursor}
              onViewModeChange={setViewMode}
              onShowMaskChange={setShowMask}
              onMaskOpacityChange={setMaskOpacity}
            />
          )}

          {currentImage && imageElement && (
            <div className="canvas-badge">
              {currentImage.name} · {imageWidth}×{imageHeight}
            </div>
          )}

          {busy && (
            <div className="canvas-badge" style={{ left: "auto", right: 12 }}>
              <span className="spinner" style={{ width: 10, height: 10 }} />
              推理中…
            </div>
          )}
        </main>

        <aside className="inspector">
          <Inspector
            model={model}
            modelError={modelError}
            boxes={currentBoxes}
            selectedBoxId={selectedBoxId}
            results={currentResults}
            threshold={threshold}
            padding={padding}
            postprocess={postprocess}
            autoRun={autoRun}
            busy={busy}
            imageWidth={Math.max(1, imageWidth)}
            imageHeight={Math.max(1, imageHeight)}
            onSelectBox={selectBox}
            onUpdateBox={handleChangeBox}
            onUpdateBoxMeta={updateBoxMeta}
            onRemoveBox={removeBox}
            onNewBox={() => setTool("draw")}
            onRun={runSelected}
            onRunAll={runAll}
            onPreview={handlePreview}
            onThresholdChange={setThreshold}
            onPaddingChange={setPadding}
            onPostprocessChange={setPostprocess}
            onAutoRunChange={setAutoRun}
            onLoadModel={() => {
              void handleLoadModel().catch(() => undefined);
            }}
          />
        </aside>
          </>
        ) : (
          <BatchPage
            model={model}
            modelError={modelError}
            onOpenSettings={() => setShowSettings(true)}
          />
        )}
      </div>

      <footer className="statusbar">
        <span className={busy ? "warn" : model?.loaded ? "ok" : "err"}>{statusText}</span>
        <span className="sep">·</span>
        {mode === "single" ? (
          <>
            <span>{currentImage ? `${imageWidth}×${imageHeight}` : "—"}</span>
            <span className="sep">·</span>
            <span>
              x {cursor.x ?? "—"} y {cursor.y ?? "—"}
            </span>
            <span className="sep">·</span>
            <span>{lastResult ? `${Math.round(lastResult.latencyMs)} ms` : "—"}</span>
            <span className="sep">·</span>
            <span>mask {lastResult ? `${(lastResult.areaRatio * 100).toFixed(2)}%` : "—"}</span>
          </>
        ) : (
          <>
            <span>批量处理</span>
            <span className="sep">·</span>
            <span>解析 / 推理 / 导出</span>
          </>
        )}
        <span className="grow" />
        <span>本地处理 · 无上传</span>
        <span className="sep">·</span>
        <span>v0.1.0</span>
      </footer>

      {dragOver && mode === "single" && (
        <div className="drop-overlay">
          <div className="drop-overlay-card">松开以导入图片</div>
        </div>
      )}

      {showSettings && (
        <SettingsDialog
          model={model}
          onClose={() => setShowSettings(false)}
          onLoad={handleLoadModel}
        />
      )}
      {showHelp && <HelpDialog onClose={() => setShowHelp(false)} />}
      {previewOpen && (
        <PreviewDialog
          data={preview}
          loading={previewLoading}
          error={previewError}
          onClose={() => setPreviewOpen(false)}
        />
      )}
      <Toaster theme={theme} position="bottom-left" richColors closeButton offset={38} />
    </div>
  );
}
