import { Scan } from "lucide-react";
import { Modal } from "./Modal";
import { dataUrl } from "../api/client";
import type { InputPreview } from "../types";

interface Props {
  data: InputPreview | null;
  loading: boolean;
  error: string | null;
  onClose(): void;
}

export function PreviewDialog({ data, loading, error, onClose }: Props) {
  return (
    <Modal
      title="模型输入预览"
      icon={<Scan size={15} />}
      onClose={onClose}
      wide
      footer={
        <button className="btn" onClick={onClose}>
          关闭
        </button>
      }
    >
      {loading && (
        <div className="empty-note">
          <span className="spinner" /> 正在生成两路输入…
        </div>
      )}
      {error && <div className="warning-note">{error}</div>}
      {data && !loading && (
        <>
          <div className="preview-grid">
            <div className="preview-card">
              <img src={dataUrl(data.full_png_base64)} alt="full branch" />
              <div className="cap">整图分支 · 直接拉伸到 768×512（不保持比例）</div>
            </div>
            <div className="preview-card">
              <img src={dataUrl(data.crop_png_base64)} alt="crop branch" />
              <div className="cap">框裁剪分支 · 等比缩放 + 黑色 letterbox</div>
            </div>
          </div>
          <div className="kv">
            <span>模型实际使用框</span>
            <span className="v">
              {data.box_used[0]}, {data.box_used[1]} → {data.box_used[2]}, {data.box_used[3]}
            </span>
          </div>
          {data.warning && <div className="warning-note">{data.warning}</div>}
          <div className="hint">
            模型输入是两路 RGB 拼接成的 6 通道张量，不能直接可视化；这里分别显示两路图像，便于检查框坐标与
            letterbox 是否正确。
          </div>
        </>
      )}
    </Modal>
  );
}
