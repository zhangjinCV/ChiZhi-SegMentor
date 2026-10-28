import { Box, CircleHelp, Images, Layers, Moon, Settings2, Sun } from "lucide-react";
import type { ModelInfo } from "../types";

interface Props {
  model: ModelInfo | null;
  modelError: string | null;
  loadingModel: boolean;
  theme: "light" | "dark";
  mode: "single" | "batch";
  onModeChange(mode: "single" | "batch"): void;
  onThemeChange(theme: "light" | "dark"): void;
  onSettings(): void;
  onHelp(): void;
}

export function TopBar(props: Props) {
  const modelState = props.loadingModel
    ? "loading"
    : props.model?.loaded
      ? "ready"
      : "error";
  const modelLabel = props.loadingModel
    ? "模型加载中"
    : props.model?.loaded
      ? `${props.model.device?.toUpperCase() ?? "CPU"} · 已就绪`
      : "模型未加载";

  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark">
          <img src="/chizhi-mark-128.png" alt="炽智实验室" draggable={false} />
        </span>
        <span>
          <div className="brand-name">炽智 SegMentor</div>
          <div className="brand-sub">框选分割工作台 · CHIZHI LAB</div>
        </span>
      </div>

      <div className="project-block">
        <span className="session-dot" title="当前为本地临时会话，批量/项目持久化在下一阶段" />
        <span className="project-name">本地会话</span>
      </div>

      <nav className="mode-tabs">
        <button
          className={`mode-tab ${props.mode === "single" ? "active" : ""}`}
          onClick={() => props.onModeChange("single")}
        >
          <Images size={13} />
          单图
        </button>
        <button
          className={`mode-tab ${props.mode === "batch" ? "active" : ""}`}
          onClick={() => props.onModeChange("batch")}
        >
          <Layers size={13} />
          批量
        </button>
        <button className="mode-tab" disabled title="项目持久化在下一阶段开放">
          <Box size={13} />
          项目
        </button>
      </nav>

      <div className="top-actions">
        <span className={`model-pill ${modelState}`} title={props.modelError ?? modelLabel}>
          <span className="dot" />
          {modelLabel}
        </span>
        <div className="theme-toggle" title="主题">
          <button
            className={props.theme === "light" ? "active" : ""}
            onClick={() => props.onThemeChange("light")}
            title="浅色"
          >
            <Sun size={13} />
          </button>
          <button
            className={props.theme === "dark" ? "active" : ""}
            onClick={() => props.onThemeChange("dark")}
            title="深色"
          >
            <Moon size={13} />
          </button>
        </div>
        <button className="icon-btn" onClick={props.onHelp} title="快捷键与帮助">
          <CircleHelp size={15} />
        </button>
        <button className="icon-btn" onClick={props.onSettings} title="设置">
          <Settings2 size={15} />
        </button>
      </div>
    </header>
  );
}
