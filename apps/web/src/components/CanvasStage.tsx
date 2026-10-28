import { useCallback, useEffect, useRef, useState } from "react";
import Konva from "konva";
import type { KonvaEventObject } from "konva/lib/Node";
import {
  Eye,
  EyeOff,
  Hand,
  Maximize2,
  Minus,
  MousePointer2,
  Plus,
  Redo2,
  SquareDashed,
  Undo2,
} from "lucide-react";
import { Image as KonvaImage, Layer, Rect, Stage, Transformer } from "react-konva";
import type { EditorBox, SegmentResult, Tool, ViewMode } from "../types";
import { useImageElement } from "../hooks/useImageElement";
import { dataUrl } from "../api/client";
import { BOX_COLORS } from "../store/editor";

const MIN_BOX = 3;

interface Props {
  image: HTMLImageElement | null;
  imageWidth: number;
  imageHeight: number;
  boxes: EditorBox[];
  selectedBoxId: string | null;
  results: Record<string, SegmentResult>;
  tool: Tool;
  viewMode: ViewMode;
  showMask: boolean;
  maskOpacity: number;
  canUndo: boolean;
  canRedo: boolean;
  onUndo(): void;
  onRedo(): void;
  onToolChange(tool: Tool): void;
  onSelectBox(id: string | null): void;
  onCreateBox(box: EditorBox): void;
  onChangeBox(id: string, patch: Partial<EditorBox>): void;
  onCursor(x: number | null, y: number | null): void;
  onViewModeChange(mode: ViewMode): void;
  onShowMaskChange(value: boolean): void;
  onMaskOpacityChange(value: number): void;
}

interface Draft {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

function normalize(draft: Draft): Draft {
  return {
    x1: Math.min(draft.x1, draft.x2),
    y1: Math.min(draft.y1, draft.y2),
    x2: Math.max(draft.x1, draft.x2),
    y2: Math.max(draft.y1, draft.y2),
  };
}

function MaskLayer({
  result,
  width,
  height,
  opacity,
}: {
  result: SegmentResult;
  width: number;
  height: number;
  opacity: number;
}) {
  const src = result.overlayBase64 ? dataUrl(result.overlayBase64) : undefined;
  const { image } = useImageElement(src);
  if (!image) return null;
  return (
    <KonvaImage
      image={image}
      x={0}
      y={0}
      width={width}
      height={height}
      opacity={opacity}
      listening={false}
    />
  );
}

export function CanvasStage(props: Props) {
  const {
    image,
    imageWidth,
    imageHeight,
    boxes,
    selectedBoxId,
    results,
    tool,
    viewMode,
    showMask,
    maskOpacity,
  } = props;

  const hostRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<Konva.Stage>(null);
  const trRef = useRef<Konva.Transformer>(null);
  const [size, setSize] = useState({ width: 900, height: 620 });
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [draft, setDraft] = useState<Draft | null>(null);
  const [spaceDown, setSpaceDown] = useState(false);
  const draftRef = useRef<Draft | null>(null);
  const interacting = useRef(false);

  draftRef.current = draft;

  useEffect(() => {
    const el = hostRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0].contentRect;
      setSize({ width: Math.max(10, rect.width), height: Math.max(10, rect.height) });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const fit = useCallback(() => {
    if (!image || size.width < 20 || size.height < 20) return;
    const pad = 54;
    const next = Math.min(
      (size.width - pad * 2) / imageWidth,
      (size.height - pad * 2) / imageHeight,
    );
    const s = Math.max(0.01, Math.min(next, 12));
    setScale(s);
    setPosition({
      x: (size.width - imageWidth * s) / 2,
      y: (size.height - imageHeight * s) / 2,
    });
  }, [image, imageWidth, imageHeight, size.width, size.height]);

  useEffect(() => {
    fit();
  }, [fit]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (/input|textarea|select/i.test(target.tagName) || target.isContentEditable)) {
        return;
      }
      if (event.code === "Space") {
        event.preventDefault();
        setSpaceDown(true);
      }
      if (event.key.toLowerCase() === "f") {
        event.preventDefault();
        fit();
      }
      if (event.key === "1" && image) {
        event.preventDefault();
        setScale(1);
        setPosition({
          x: (size.width - imageWidth) / 2,
          y: (size.height - imageHeight) / 2,
        });
      }
    };
    const onKeyUp = (event: KeyboardEvent) => {
      if (event.code === "Space") setSpaceDown(false);
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, [fit, image, imageWidth, imageHeight, size.width, size.height]);

  useEffect(() => {
    const transformer = trRef.current;
    if (!transformer) return;
    if (!selectedBoxId || tool !== "select") {
      transformer.nodes([]);
      transformer.getLayer()?.batchDraw();
      return;
    }
    const node = stageRef.current?.findOne(`#box-${selectedBoxId}`);
    if (node) {
      transformer.nodes([node]);
    } else {
      transformer.nodes([]);
    }
    transformer.getLayer()?.batchDraw();
  }, [selectedBoxId, boxes, tool]);

  const pointerInImage = useCallback(() => {
    const stage = stageRef.current;
    if (!stage) return null;
    const pointer = stage.getPointerPosition();
    if (!pointer) return null;
    const x = (pointer.x - stage.x()) / stage.scaleX();
    const y = (pointer.y - stage.y()) / stage.scaleY();
    return { x, y };
  }, []);

  const clampPoint = useCallback(
    (p: { x: number; y: number }) => ({
      x: Math.max(0, Math.min(imageWidth, p.x)),
      y: Math.max(0, Math.min(imageHeight, p.y)),
    }),
    [imageWidth, imageHeight],
  );

  const onWheel = (event: KonvaEventObject<WheelEvent>) => {
    event.evt.preventDefault();
    const stage = stageRef.current;
    if (!stage) return;
    const pointer = stage.getPointerPosition();
    if (!pointer) return;
    const oldScale = stage.scaleX();
    const mousePointTo = {
      x: (pointer.x - stage.x()) / oldScale,
      y: (pointer.y - stage.y()) / oldScale,
    };
    const direction = event.evt.deltaY > 0 ? 0.9 : 1.1;
    const nextScale = Math.max(0.02, Math.min(24, oldScale * direction));
    setScale(nextScale);
    setPosition({
      x: pointer.x - mousePointTo.x * nextScale,
      y: pointer.y - mousePointTo.y * nextScale,
    });
  };

  const onMouseDown = (event: KonvaEventObject<MouseEvent>) => {
    const stage = stageRef.current;
    if (!stage || !image) return;
    if (event.evt.button !== 0) return;
    if (event.target !== stage) return;
    if (tool === "select") {
      props.onSelectBox(null);
      return;
    }
    if (tool !== "draw") return;
    const point = pointerInImage();
    if (!point) return;
    const clamped = clampPoint(point);
    const next = { x1: clamped.x, y1: clamped.y, x2: clamped.x, y2: clamped.y };
    setDraft(next);
    draftRef.current = next;
  };

  const onMouseMove = () => {
    if (interacting.current) return;
    const point = pointerInImage();
    if (point) {
      props.onCursor(Math.round(point.x), Math.round(point.y));
      if (draftRef.current) {
        const clamped = clampPoint(point);
        const next = { ...draftRef.current, x2: clamped.x, y2: clamped.y };
        draftRef.current = next;
        setDraft(next);
      }
    }
  };

  const finishDraft = () => {
    const current = draftRef.current;
    if (!current) return;
    const box = normalize(current);
    setDraft(null);
    draftRef.current = null;
    if (box.x2 - box.x1 < MIN_BOX || box.y2 - box.y1 < MIN_BOX) return;
    props.onCreateBox({
      id: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}`,
      x1: Math.round(box.x1),
      y1: Math.round(box.y1),
      x2: Math.round(box.x2),
      y2: Math.round(box.y2),
      label: "目标",
    });
  };

  const onBoxDragEnd = (event: KonvaEventObject<DragEvent>, box: EditorBox) => {
    interacting.current = false;
    const width = box.x2 - box.x1;
    const height = box.y2 - box.y1;
    const x1 = Math.max(0, Math.min(imageWidth - width, event.target.x()));
    const y1 = Math.max(0, Math.min(imageHeight - height, event.target.y()));
    event.target.position({ x: x1, y: y1 });
    props.onChangeBox(box.id, {
      x1: Math.round(x1),
      y1: Math.round(y1),
      x2: Math.round(x1 + width),
      y2: Math.round(y1 + height),
    });
  };

  const onTransformEnd = (box: EditorBox) => {
    interacting.current = false;
    const node = stageRef.current?.findOne(`#box-${box.id}`) as Konva.Rect | undefined;
    if (!node) return;
    const scaleX = node.scaleX();
    const scaleY = node.scaleY();
    node.scaleX(1);
    node.scaleY(1);
    const width = Math.max(MIN_BOX, node.width() * scaleX);
    const height = Math.max(MIN_BOX, node.height() * scaleY);
    const x1 = Math.max(0, Math.min(imageWidth - width, node.x()));
    const y1 = Math.max(0, Math.min(imageHeight - height, node.y()));
    props.onChangeBox(box.id, {
      x1: Math.round(x1),
      y1: Math.round(y1),
      x2: Math.round(x1 + width),
      y2: Math.round(y1 + height),
    });
  };

  const zoomBy = (factor: number) => {
    const stage = stageRef.current;
    if (!stage) return;
    const center = { x: size.width / 2, y: size.height / 2 };
    const oldScale = stage.scaleX();
    const pointTo = {
      x: (center.x - stage.x()) / oldScale,
      y: (center.y - stage.y()) / oldScale,
    };
    const nextScale = Math.max(0.02, Math.min(24, oldScale * factor));
    setScale(nextScale);
    setPosition({
      x: center.x - pointTo.x * nextScale,
      y: center.y - pointTo.y * nextScale,
    });
  };

  const cursor =
    spaceDown || tool === "pan" ? "grab" : tool === "draw" ? "crosshair" : "default";

  return (
    <div ref={hostRef} className="canvas-host" style={{ cursor }}>
      <div className="canvas-toolbar" onMouseDown={(event) => event.stopPropagation()}>
        <button
          className={`tool-btn ${tool === "select" ? "active" : ""}`}
          onClick={() => props.onToolChange("select")}
          title="选择 / 移动框 (V)"
        >
          <MousePointer2 size={14} />
        </button>
        <button
          className={`tool-btn ${tool === "draw" ? "active" : ""}`}
          onClick={() => props.onToolChange("draw")}
          title="画框 (B)"
        >
          <SquareDashed size={14} />
        </button>
        <button
          className={`tool-btn ${tool === "pan" ? "active" : ""}`}
          onClick={() => props.onToolChange("pan")}
          title="平移 (H / 空格拖动)"
        >
          <Hand size={14} />
        </button>
        <div className="toolbar-divider" />
        <button
          className="tool-btn"
          onClick={props.onUndo}
          disabled={!props.canUndo}
          title="撤销 (Ctrl+Z)"
        >
          <Undo2 size={14} />
        </button>
        <button
          className="tool-btn"
          onClick={props.onRedo}
          disabled={!props.canRedo}
          title="重做 (Ctrl+Y)"
        >
          <Redo2 size={14} />
        </button>
        <div className="toolbar-divider" />
        <div className="view-switch">
          <button
            className={viewMode === "overlay" ? "active" : ""}
            onClick={() => props.onViewModeChange("overlay")}
          >
            叠加
          </button>
          <button
            className={viewMode === "original" ? "active" : ""}
            onClick={() => props.onViewModeChange("original")}
          >
            原图
          </button>
        </div>
        <button
          className={`tool-btn ${showMask ? "active" : ""}`}
          onClick={() => props.onShowMaskChange(!showMask)}
          title={showMask ? "隐藏 mask" : "显示 mask"}
        >
          {showMask ? <Eye size={14} /> : <EyeOff size={14} />}
        </button>
        <div className="opacity-control">
          <span>透明度</span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={maskOpacity}
            onChange={(event) => props.onMaskOpacityChange(Number(event.target.value))}
            disabled={!showMask || viewMode === "original"}
          />
        </div>
        <div className="toolbar-divider" />
        <button className="tool-btn" onClick={() => zoomBy(0.85)} title="缩小">
          <Minus size={14} />
        </button>
        <span className="zoom-readout">{Math.round(scale * 100)}%</span>
        <button className="tool-btn" onClick={() => zoomBy(1.18)} title="放大">
          <Plus size={14} />
        </button>
        <button className="tool-btn" onClick={fit} title="适应窗口 (F)">
          <Maximize2 size={14} />
        </button>
      </div>

      <Stage
        ref={stageRef}
        width={size.width}
        height={size.height}
        scaleX={scale}
        scaleY={scale}
        x={position.x}
        y={position.y}
        draggable={tool === "pan" || spaceDown}
        onDragStart={() => {
          interacting.current = true;
        }}
        onDragEnd={(event) => {
          interacting.current = false;
          setPosition({ x: event.target.x(), y: event.target.y() });
        }}
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={finishDraft}
        onMouseLeave={() => {
          props.onCursor(null, null);
          if (draftRef.current) {
            draftRef.current = null;
            setDraft(null);
          }
        }}
      >
        <Layer listening={false}>
          {image && (
            <KonvaImage
              image={image}
              x={0}
              y={0}
              width={imageWidth}
              height={imageHeight}
            />
          )}
        </Layer>

        {showMask && viewMode === "overlay" && (
          <Layer listening={false}>
            {Object.values(results).map((result) => (
              <MaskLayer
                key={result.boxId}
                result={result}
                width={imageWidth}
                height={imageHeight}
                opacity={maskOpacity}
              />
            ))}
          </Layer>
        )}

        <Layer>
          {boxes.map((box, index) => {
            const selected = box.id === selectedBoxId;
            const color = BOX_COLORS[index % BOX_COLORS.length];
            return (
              <Rect
                key={box.id}
                id={`box-${box.id}`}
                x={Math.min(box.x1, box.x2)}
                y={Math.min(box.y1, box.y2)}
                width={Math.abs(box.x2 - box.x1)}
                height={Math.abs(box.y2 - box.y1)}
                stroke={color}
                strokeWidth={1.6}
                strokeScaleEnabled={false}
                fill={selected ? `${color}18` : "transparent"}
                draggable={tool === "select" && !spaceDown}
                listening={tool === "select" && !spaceDown}
                hitStrokeWidth={12}
                onClick={() => props.onSelectBox(box.id)}
                onTap={() => props.onSelectBox(box.id)}
                onDragStart={() => {
                  interacting.current = true;
                }}
                onDragEnd={(event) => onBoxDragEnd(event, box)}
                onTransformEnd={() => onTransformEnd(box)}
              />
            );
          })}
          {draft &&
            (() => {
              const d = normalize(draft);
              return (
                <Rect
                  x={d.x1}
                  y={d.y1}
                  width={d.x2 - d.x1}
                  height={d.y2 - d.y1}
                  stroke="#f59e0b"
                  strokeWidth={1.6}
                  strokeScaleEnabled={false}
                  dash={[6, 4]}
                  fill="rgba(245,158,11,0.10)"
                  listening={false}
                />
              );
            })()}
        </Layer>

        <Layer>
          <Transformer
            ref={trRef}
            rotateEnabled={false}
            flipEnabled={false}
            keepRatio={false}
            ignoreStroke
            anchorSize={7}
            anchorCornerRadius={2}
            borderStroke="#f59e0b"
            anchorStroke="#f59e0b"
            anchorFill="#ffffff"
            borderStrokeWidth={1.2}
            onTransformStart={() => {
              interacting.current = true;
            }}
            boundBoxFunc={(oldBox, newBox) => {
              if (Math.abs(newBox.width) < MIN_BOX || Math.abs(newBox.height) < MIN_BOX) {
                return oldBox;
              }
              if (
                newBox.x < 0 ||
                newBox.y < 0 ||
                newBox.x + newBox.width > imageWidth ||
                newBox.y + newBox.height > imageHeight
              ) {
                return oldBox;
              }
              return newBox;
            }}
          />
        </Layer>
      </Stage>
    </div>
  );
}
