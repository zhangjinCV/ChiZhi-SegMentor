import { CircleHelp } from "lucide-react";
import { Modal } from "./Modal";

const SHORTCUTS: Array<[string[], string]> = [
  [["V"], "选择 / 移动框"],
  [["B"], "画框"],
  [["H"], "平移画布"],
  [["Space"], "临时平移（按住拖动）"],
  [["F"], "适应窗口"],
  [["1"], "100% 缩放"],
  [["Enter"], "重新分割选中框"],
  [["Delete"], "删除选中框"],
  [["←", "→"], "微调框位置（Shift ×10）"],
  [["Alt", "← / →"], "上一张 / 下一张"],
  [["Ctrl", "O"], "导入图片"],
  [["Esc"], "取消画框 / 取消选择"],
];

export function HelpDialog({ onClose }: { onClose(): void }) {
  return (
    <Modal title="快捷键与帮助" icon={<CircleHelp size={15} />} onClose={onClose}>
      <div className="shortcut-grid">
        {SHORTCUTS.map(([keys, label]) => (
          <div className="shortcut-row" key={label}>
            <span>{label}</span>
            <span className="shortcut-keys">
              {keys.map((key) => (
                <span className="kbd" key={key}>
                  {key}
                </span>
              ))}
            </span>
          </div>
        ))}
      </div>
      <div className="hint">
        <strong>使用建议：</strong>一个框尽量只框一个目标；模型是框内前景二分类，label
        仅用于组织和导出。mask 默认按训练配置（阈值 0.5、无后处理）生成，可在右侧“分割参数”中调整。
      </div>
      <div className="hint">
        图片和推理全部在本机完成，不会上传到任何服务器。模型与图片始终留在本地。
      </div>
    </Modal>
  );
}
