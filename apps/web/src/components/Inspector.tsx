import { useEffect, useState } from "react";
import {
  Copy,
  Cpu,
  Crosshair,
  Download,
  Plus,
  RefreshCw,
  Scan,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import type { PostprocessOptions } from "../api/client";
import { dataUrl } from "../api/client";
import type { EditorBox, ModelInfo, SegmentResult } from "../types";
import { BOX_COLORS } from "../store/editor";

interface Props {
  model: ModelInfo | null;
  modelError: string | null;
  boxes: EditorBox[];
  selectedBoxId: string | null;
  results: Record<string, SegmentResult>;
  threshold: number;
  padding: number;
  postprocess: PostprocessOptions;
  autoRun: boolean;
  busy: boolean;
  imageWidth: number;
  imageHeight: number;
  onSelectBox(id: string): void;
  onUpdateBox(id: string, patch: Partial<EditorBox>): void;
  onUpdateBoxMeta(id: string, patch: Partial<EditorBox>): void;
  onRemoveBox(id: string): void;
  onNewBox(): void;
  onRun(boxId?: string): void;
  onRunAll(): void;
  onPreview(box: EditorBox): void;
  onThresholdChange(value: number): void;
  onPaddingChange(value: number): void;
  onPostprocessChange(patch: Partial<PostprocessOptions>): void;
  onAutoRunChange(value: boolean): void;
  onLoadModel(): void;
}

function NumberField({
  label,
  value,
  min,
  max,
  step = 1,
  disabled,
  onCommit,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  disabled?: boolean;
  onCommit(value: number): void;
}) {
  const [text, setText] = useState(String(value));
  useEffect(() => setText(String(value)), [value]);

  const commit = () => {
    const parsed = Number(text);
    if (!Number.isFinite(parsed)) {
      setText(String(value));
      return;
    }
    const clamped = Math.max(min, Math.min(max, parsed));
    onCommit(clamped);
    setText(String(clamped));
  };

  return (
    <div className="field">
      <label>{label}</label>
      <input
        className="input"
        type="number"
        value={text}
        step={step}
        disabled={disabled}
        onChange={(event) => setText(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.currentTarget.blur();
          }
        }}
      />
    </div>
  );
}

function LabelField({
  value,
  disabled,
  onCommit,
}: {
  value: string;
  disabled?: boolean;
  onCommit(value: string): void;
}) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const commit = () => {
    const next = text.trim();
    if (next !== value) onCommit(next);
  };
  return (
    <div className="field">
      <label>标签（仅组织/导出，不参与推理）</label>
      <input
        className="input"
        style={{ fontFamily: "var(--font-sans)" }}
        value={text}
        disabled={disabled}
        onChange={(event) => setText(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.currentTarget.blur();
        }}
      />
    </div>
  );
}

function downloadBase64(base64: string, name: string) {
  const anchor = document.createElement("a");
  anchor.href = base64.startsWith("data:") ? base64 : dataUrl(base64);
  anchor.download = name;
  anchor.click();
}

async function copyPng(base64: string) {
  const blob = await (await fetch(dataUrl(base64))).blob();
  await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
}

export function Inspector(props: Props) {
  const {
    model,
    modelError,
    boxes,
    selectedBoxId,
    results,
    threshold,
    padding,
    postprocess,
    autoRun,
    busy,
    imageWidth,
    imageHeight,
  } = props;

  const selectedIndex = boxes.findIndex((box) => box.id === selectedBoxId);
  const selected = selectedIndex >= 0 ? boxes[selectedIndex] : null;
  const result = selected ? results[selected.id] : undefined;

  return (
    <div className="panel-scroll inspector-scroll">
      <section className="section">
        <div className="section-head">
          <Crosshair size={13} />
          框选提示
          <span className="spacer" />
          <button className="btn btn-sm btn-ghost" onClick={props.onNewBox}>
            <Plus size={12} />
            新建框
          </button>
        </div>
        <div className="section-body">
          {boxes.length === 0 ? (
            <div className="empty-note">
              在画布上拖拽即可画框。
              <br />
              画完会自动分割（可在下方关闭）。
            </div>
          ) : (
            <div className="box-list">
              {boxes.map((box, index) => (
                <div
                  key={box.id}
                  className={`box-row ${box.id === selectedBoxId ? "selected" : ""}`}
                  onClick={() => props.onSelectBox(box.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") props.onSelectBox(box.id);
                  }}
                >
                  <span
                    className="box-swatch"
                    style={{ background: BOX_COLORS[index % BOX_COLORS.length] }}
                  />
                  <span className="box-name">
                    {box.label?.trim() || `框 ${index + 1}`}
                    <span className="box-coords" style={{ display: "block" }}>
                      {box.x1},{box.y1} → {box.x2},{box.y2}
                    </span>
                  </span>
                  <button
                    className="mini-btn"
                    title="删除框"
                    onClick={(event) => {
                      event.stopPropagation();
                      props.onRemoveBox(box.id);
                    }}
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {selected && (
            <>
              <div className="divider" />
              <LabelField
                value={selected.label ?? ""}
                disabled={busy}
                onCommit={(label) => props.onUpdateBoxMeta(selected.id, { label })}
              />
              <div className="coord-grid">
                <NumberField
                  label="X1"
                  value={selected.x1}
                  min={0}
                  max={imageWidth}
                  disabled={busy}
                  onCommit={(value) =>
                    props.onUpdateBox(selected.id, {
                      x1: Math.max(0, Math.min(value, selected.x2 - 3)),
                    })
                  }
                />
                <NumberField
                  label="Y1"
                  value={selected.y1}
                  min={0}
                  max={imageHeight}
                  disabled={busy}
                  onCommit={(value) =>
                    props.onUpdateBox(selected.id, {
                      y1: Math.max(0, Math.min(value, selected.y2 - 3)),
                    })
                  }
                />
                <NumberField
                  label="X2"
                  value={selected.x2}
                  min={0}
                  max={imageWidth}
                  disabled={busy}
                  onCommit={(value) =>
                    props.onUpdateBox(selected.id, {
                      x2: Math.min(imageWidth, Math.max(value, selected.x1 + 3)),
                    })
                  }
                />
                <NumberField
                  label="Y2"
                  value={selected.y2}
                  min={0}
                  max={imageHeight}
                  disabled={busy}
                  onCommit={(value) =>
                    props.onUpdateBox(selected.id, {
                      y2: Math.min(imageHeight, Math.max(value, selected.y1 + 3)),
                    })
                  }
                />
              </div>
              <div className="btn-row">
                <button className="btn btn-primary" onClick={() => props.onRun(selected.id)} disabled={busy}>
                  {busy ? <span className="spinner" /> : <RefreshCw size={13} />}
                  重新分割
                </button>
                <button className="btn" onClick={() => props.onPreview(selected)} disabled={busy}>
                  <Scan size={13} />
                  输入预览
                </button>
              </div>
              <div className="hint">
                一个框尽量只框一个目标；框内多目标会合并到同一 mask。框越贴近目标，效果通常越好。
              </div>
            </>
          )}

          {boxes.length > 1 && (
            <button className="btn btn-block" onClick={props.onRunAll} disabled={busy}>
              <RefreshCw size={13} />
              全部分割（{boxes.length} 个框）
            </button>
          )}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <Scan size={13} />
          结果
          <span className="spacer" />
          {result && <span className="badge success">完成</span>}
        </div>
        <div className="section-body">
          {!selected ? (
            <div className="empty-note">选择一个框查看分割结果。</div>
          ) : result ? (
            <>
              <div className="result-grid">
                <div className="stat">
                  <div className="k">面积</div>
                  <div className="v">{result.areaPx.toLocaleString()} px</div>
                </div>
                <div className="stat">
                  <div className="k">占全图</div>
                  <div className="v">{(result.areaRatio * 100).toFixed(2)}%</div>
                </div>
                <div className="stat">
                  <div className="k">平均概率</div>
                  <div className="v">
                    {result.meanProb != null ? (result.meanProb * 100).toFixed(1) + "%" : "—"}
                  </div>
                </div>
                <div className="stat">
                  <div className="k">耗时</div>
                  <div className="v">{Math.round(result.latencyMs)} ms</div>
                </div>
              </div>
              {result.warning && <div className="warning-note">{result.warning}</div>}
              {result.areaPx === 0 && (
                <div className="warning-note">
                  框内未检测到目标。可尝试扩大框、降低阈值或检查框的位置。
                </div>
              )}
              <div className="mask-preview">
                <img
                  src={dataUrl(result.overlayBase64 ?? result.maskBase64)}
                  alt="mask preview"
                  draggable={false}
                />
              </div>
              <div className="btn-row">
                <button
                  className="btn"
                  onClick={() => {
                    try {
                      downloadBase64(result.maskBase64, `${selected.label || "mask"}_${selected.x1}_${selected.y1}.png`);
                    } catch {
                      toast.error("下载失败");
                    }
                  }}
                >
                  <Download size={13} />
                  下载 mask
                </button>
                <button
                  className="btn"
                  onClick={() => {
                    copyPng(result.maskBase64).catch(() => toast.error("复制失败，请检查剪贴板权限"));
                  }}
                >
                  <Copy size={13} />
                  复制
                </button>
              </div>
            </>
          ) : (
            <div className="empty-note">
              {busy ? "正在分割…" : "这个框还没有结果。点击“重新分割”生成 mask。"}
            </div>
          )}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <SlidersHorizontal size={13} />
          分割参数
        </div>
        <div className="section-body">
          <div className="field">
            <label>
              阈值 <span style={{ color: "var(--muted-2)" }}>（训练默认 0.5）</span>
            </label>
            <div className="slider-row">
              <input
                type="range"
                min={0.05}
                max={0.95}
                step={0.01}
                value={threshold}
                onChange={(event) => props.onThresholdChange(Number(event.target.value))}
              />
              <span className="slider-value">{threshold.toFixed(2)}</span>
            </div>
          </div>
          <NumberField
            label="框外扩 padding (px)"
            value={padding}
            min={0}
            max={512}
            disabled={busy}
            onCommit={props.onPaddingChange}
          />
          <div className="divider" />
          <label className="check-row">
            <input
              type="checkbox"
              checked={autoRun}
              onChange={(event) => props.onAutoRunChange(event.target.checked)}
            />
            画完 / 改完框自动分割
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={postprocess.keepLargest}
              onChange={(event) => props.onPostprocessChange({ keepLargest: event.target.checked })}
            />
            仅保留最大连通域
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={postprocess.fillHoles}
              onChange={(event) => props.onPostprocessChange({ fillHoles: event.target.checked })}
            />
            填充内部空洞
          </label>
          <div className="coord-grid">
            <NumberField
              label="最小面积 (px)"
              value={postprocess.minArea}
              min={0}
              max={1000000}
              disabled={busy || postprocess.keepLargest}
              onCommit={(value) => props.onPostprocessChange({ minArea: Math.round(value) })}
            />
            <NumberField
              label="平滑半径 (px)"
              value={postprocess.smoothRadius}
              min={0}
              max={32}
              disabled={busy}
              onCommit={(value) => props.onPostprocessChange({ smoothRadius: Math.round(value) })}
            />
          </div>
          <div className="hint">
            默认参数与训练验证一致。后处理会改变 mask，导出前建议先对比原始结果。
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <Cpu size={13} />
          模型
          <span className="spacer" />
          {model?.loaded ? <span className="badge success">已加载</span> : <span className="badge warn">未加载</span>}
        </div>
        <div className="section-body">
          {model?.loaded ? (
            <>
              <div className="kv">
                <span>架构</span>
                <span className="v">RepViT-M1.1 + PNet · {model.parameters_million}M</span>
              </div>
              <div className="kv">
                <span>输入</span>
                <span className="v">
                  6 × {model.input_height} × {model.input_width}
                </span>
              </div>
              <div className="kv">
                <span>设备</span>
                <span className="v">{model.device}</span>
              </div>
              <div className="kv">
                <span>Checkpoint</span>
                <span className="v" title={model.checkpoint}>
                  {model.checkpoint_name}
                </span>
              </div>
              <div className="kv">
                <span>SHA256</span>
                <span className="v">{model.model_hash?.slice(0, 12)}…</span>
              </div>
            </>
          ) : (
            <>
              <div className="warning-note">{modelError ?? "模型尚未加载。"}</div>
              <button className="btn btn-block" onClick={props.onLoadModel}>
                <Cpu size={13} />
                加载默认模型
              </button>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
