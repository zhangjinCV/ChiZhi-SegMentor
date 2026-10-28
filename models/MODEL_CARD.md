# Model Card — Chizhi SegMentor (RepViT-M1.1 + PNet)

## 基本信息

| 项 | 值 |
|---|---|
| 任务 | 框提示（box-prompted）单通道前景分割 |
| 架构 | RepViT-M1.1 backbone + PNet 风格 UNet 解码器（4 级深监督 + boundary 头） |
| 参数量 | 约 10.33 M |
| 权重文件 | `boxmask_repvit_best_snapshot.pth` |
| 文件大小 | 39.8 MiB (41,710,353 bytes) |
| SHA256 | `17b8f2d5fc0e65b1d6ec1b0c8ec123452fba02e4ba4dc784c95d4ed288f82d4c` |
| 快照时间 | 2026-10-28（训练仍在进行，快照已冻结） |
| 来源 | `model6ch/runs/repvit_pnet/best.pth`（训练仓库相对路径） |

## 输入契约

模型输入固定为 `6 × 512 × 768` float32：

1. **前 3 通道**：原图 RGB 直接拉伸到 `768×512`（不保持长宽比，不 padding）。
2. **后 3 通道**：用框从原图裁剪，再 letterbox（等比缩放 + 纯黑 `(0,0,0)` 填充）到 `768×512`。
3. 归一化：uint8 → `/255` → 6 个通道统一使用 ImageNet mean/std：
   `mean=[0.485,0.456,0.406]×2`，`std=[0.229,0.224,0.225]×2`。
4. 框格式：原图像素坐标 PIL bbox `(x0,y0,x1,y1)`，右/下为开区间；越界会 clamp，宽或高 <2px 回退整图。

注意：这里**不是**在图上画框线，也不是 box mask。训练时的框来自 GT mask 的外接框。

## 输出契约

- `net(x)` 返回 9 个张量；最终 mask 是 **`out[4]`**（`[B,1,512,768]`）。
- 后处理：`sigmoid` → 阈值 0.5 → 二值。
- 概率图需双线性插值回原图尺寸后再阈值化；不要直接最近邻放大二值图。
- 程序内部会保存原图尺寸的二值 PNG（0/255）。

## 指标

来自训练日志的验证结果（n=2700）：

- MAE：0.02517
- IoU：0.83954（验证框来自 GT mask 外接框）

**这不是任意手绘框的指标。** 部署时应使用真实手绘框与 ±10% 扰动框重新评测；README/模型卡应明确“框越贴近目标通常越好”。

### 开发期 demo 抽样（非基准）

仅为 README 选图做的快速抽样，样本小、框来自 GT 外接框，**不能当作整体性能指标**：

- DUTS-TR：n=60，框外扩约 3%，mean IoU 0.963，median 0.974。
- NBCM/COD10K：20 类 × 3 张，n=60，框外扩约 2%，mean IoU 0.783，median 0.878；伪装目标难度差异很大。

## 适用范围与限制

- 训练数据由 SA-1B 与 pnet_data（COD / SOD / DIS，排除 COCONUT）组成；模型是类别无关的前景分割器，并不只针对 tank / soldier。README 中的 NBCM/COD10K 伪装目标与 DUTS-TR 通用目标示例均为真实输出。
- 单框单目标效果最好；框内多个目标会合并到同一 mask。
- 类别无关：label 仅用于组织与导出。
- 验证 IoU 使用 GT mask 外接框；真实手绘框、偏松/偏紧框的系统评测仍需补充。
- 未经过 mask 手工修整；首版软件也不提供画笔/橡皮（v1.1）。
- CPU 可运行，但批量吞吐取决于机器；CUDA 版需单独验证。

## 许可与合规

- 代码（含 vendored RepViT）为 Apache-2.0；上游 RepViT 许可证见 `backend/boxmask/vendor/REPVIT_LICENSE`。
- 权重作者已确认可公开下载；详见 [MODEL_LICENSE.md](MODEL_LICENSE.md)。训练数据来源、用途限制与再分发条件需由作者在正式 Release 前补充确认。
- README 中的 NBCM/COD10K、DUTS-TR、Pixabay 与作者提供的 lizard 示例仅用于展示，版权与使用条款归原数据集/图库作者，**不按 Apache-2.0 授权**；项目作者已确认可用于本仓库公开演示。详见 [docs/images/DATASETS.md](../docs/images/DATASETS.md)；二次再分发请继续遵守原数据集/图库条款。
- 炽智实验室 logo/名称不在 Apache-2.0 内。

## 引用

本项目的 6 通道 box-prompted 分割模型与训练思路参考了：

Jin Zhang, Ruiheng Zhang, Yanjiao Shi, Zhe Cao, Nian Liu, Fahad Shahbaz Khan. “Learning Camouflaged Object Detection from Noisy Pseudo Label.” ECCV 2024, pp. 158–174. DOI: 10.1007/978-3-031-73232-4_9

```bibtex
@InProceedings{10.1007/978-3-031-73232-4_9,
  author    = {Zhang, Jin and Zhang, Ruiheng and Shi, Yanjiao and Cao, Zhe and Liu, Nian and Khan, Fahad Shahbaz},
  editor    = {Leonardis, Ale{\v{s}} and Ricci, Elisa and Roth, Stefan and Russakovsky, Olga and Sattler, Torsten and Varol, G{\"u}l},
  title     = {Learning Camouflaged Object Detection from Noisy Pseudo Label},
  booktitle = {Computer Vision -- ECCV 2024},
  year      = {2025},
  publisher = {Springer Nature Switzerland},
  address   = {Cham},
  pages     = {158--174},
  isbn      = {978-3-031-73232-4},
  doi       = {10.1007/978-3-031-73232-4_9}
}
```
