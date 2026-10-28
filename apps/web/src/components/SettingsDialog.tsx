import { useState } from "react";
import { Cpu, FolderSearch, Settings2 } from "lucide-react";
import { Modal } from "./Modal";
import type { ModelInfo } from "../types";

interface Props {
  model: ModelInfo | null;
  onClose(): void;
  onLoad(checkpoint?: string, device?: string): Promise<void>;
}

function formatSize(bytes?: number): string {
  if (!bytes) return "—";
  if (bytes > 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.round(bytes / 1024)} KB`;
}

export function SettingsDialog({ model, onClose, onLoad }: Props) {
  const [checkpoint, setCheckpoint] = useState(model?.checkpoint ?? "");
  const [device, setDevice] = useState((model?.device ?? "auto").toLowerCase());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setLoading(true);
    setError(null);
    try {
      await onLoad(checkpoint.trim() || undefined, device);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      title="设置"
      icon={<Settings2 size={15} />}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            关闭
          </button>
          <button className="btn btn-primary" onClick={submit} disabled={loading}>
            {loading ? <span className="spinner" /> : <Cpu size={13} />}
            加载模型
          </button>
        </>
      }
    >
      <div className="field">
        <label>Checkpoint 路径</label>
        <div style={{ display: "flex", gap: 6 }}>
          <input
            className="input"
            style={{ fontFamily: "var(--font-mono)", fontSize: 10.5 }}
            value={checkpoint}
            onChange={(event) => setCheckpoint(event.target.value)}
            placeholder="留空使用默认模型"
            spellCheck={false}
          />
          <button
            className="btn"
            onClick={() => setCheckpoint("")}
            title="使用应用内置默认路径"
          >
            <FolderSearch size={13} />
            默认
          </button>
        </div>
        <div className="hint">
          默认路径为项目内的 <code>models/boxmask_repvit_best_snapshot.pth</code>。也可以选择任意
          RepViTPNet state_dict（约 39.8MB）。
        </div>
      </div>

      <div className="field">
        <label>推理设备</label>
        <select className="input" value={device} onChange={(event) => setDevice(event.target.value)}>
          <option value="auto">自动（CUDA → CPU）</option>
          <option value="cuda">CUDA（需要 CUDA 版安装包）</option>
          <option value="cpu">CPU</option>
        </select>
        <div className="hint">CPU 版安装包不支持 CUDA；选择 CUDA 会返回明确错误。</div>
      </div>

      <div className="divider" />

      <div className="kv">
        <span>当前状态</span>
        <span className="v">{model?.loaded ? "已加载" : "未加载"}</span>
      </div>
      <div className="kv">
        <span>模型文件</span>
        <span className="v" title={model?.checkpoint}>
          {model?.checkpoint_name ?? "—"}
        </span>
      </div>
      <div className="kv">
        <span>文件大小</span>
        <span className="v">{formatSize(model?.checkpoint_size)}</span>
      </div>
      <div className="kv">
        <span>设备</span>
        <span className="v">{model?.device ?? "—"}</span>
      </div>
      <div className="kv">
        <span>SHA256</span>
        <span className="v">{model?.model_hash ? `${model.model_hash.slice(0, 20)}…` : "—"}</span>
      </div>
      <div className="kv">
        <span>加载耗时</span>
        <span className="v">{model?.load_seconds ? `${model.load_seconds.toFixed(2)} s` : "—"}</span>
      </div>

      {error && <div className="warning-note">{error}</div>}
    </Modal>
  );
}
