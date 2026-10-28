# 示例图片 / Demo image credits

README 中的 demo 只使用少量研究数据图片来展示模型输出，**这些图片不属于 Apache-2.0 代码许可**。图片与标注的版权/使用条款归原数据集/图库作者；项目作者已确认这些示例可用于本仓库公开演示。若你要二次再分发，请继续遵守原数据集/图库条款。

## NBCM / COD10K

用于：

- `demo-hero.gif` — Butterfly / Seahorse
- `demo-grid.jpg` — Snake / Cicada / Batfish / Grasshopper / Butterfly
- `batch-import.jpg` / `batch-workspace.jpg` — Seahorse

来源：本地研究数据副本，文件名保留 `COD10K-CAM-...` 前缀，原图来自 **COD10K**（*Camouflaged Object Detection*, CVPR 2020）及其衍生整理。原始数据包含 GT mask 标注；demo 只把原图和框作为输入，图上显示的 mask 全部是模型重新推理结果（不是 GT）。

## DUTS-TR

用于：

- `demo-general.jpg` — Apple / Corgi / Parrot / Car
- `demo-grid.jpg` — Birds（一框两只）
- `demo-ui.gif` — Birds（双框，真实应用界面）
- `single-workspace.jpg` / `model-input-preview.jpg` — Birds（双框）
- `batch-import.jpg` / `batch-workspace.jpg` — Birds

来源：本地研究数据副本（DUTS-TR），原图来自 **DUTS**（*DUTS: Learning to Detect Salient Objects with Image-level Supervision*, CVPR 2017）或其 ImageNet/其他公开图像来源。DUTS-TR 常用于显著性目标检测训练/测试，具体再分发条件以其官方发布为准。

## Project-provided lizard replacement

用于：

- `demo-hero.gif` — Lizard（第三幕）
- `batch-import.jpg` / `batch-workspace.jpg` — Lizard

说明：这张蜥蜴替换图由项目作者提供，并确认允许在本仓库公开演示；原始出处未记录。它不按 Apache-2.0 授权。

## Pixabay / Flamingo

用于：

- `demo-flamingo.gif` — 640×480 粉红火烈鸟（文件名 `pink-flamingo-862792_640.jpg`，Pixabay ID 862792）

说明：按文件名判断该图来自 Pixabay（ID 862792），适用 Pixabay Content License；项目作者已确认用于本仓库公开演示。图片只用于展示，不按 Apache-2.0 授权。

## 如果要发布到不允许再分发示例的场合

删除 `docs/images/demo-hero.gif`、`demo-ui.gif`、`demo-grid.jpg`、`demo-general.jpg`、`demo-flamingo.gif`，并替换 README / README.en.md 中对应图片引用即可；软件与模型功能不受影响。也可以换成自己拥有版权的图片重新生成 demo。

## 生成说明

- demo 使用冻结权重 `models/boxmask_repvit_best_snapshot.pth`，阈值 0.5、padding 0；框大多为 GT/目标外接框外扩约 2–3%，火烈鸟为手工覆盖三只的多目标框。
- GIF 为 README 展示做过缩放和调色板压缩；mask 结果未做手工修改。
- 生成脚本没有随仓库发布，避免把本地数据路径和临时文件带进开源仓库。

## English summary

The README demos use a few images from local research copies of NBCM/COD10K (butterfly, seahorse, snake, lizard, cicada, batfish, grasshopper), DUTS-TR (two birds, apple, corgi, parrot, car), a project-provided lizard replacement (source to confirm), and a Pixabay flamingo image (ID 862792). They are included for illustration only and remain under the original dataset terms; they are **not** Apache-2.0. The masks shown are fresh model outputs, not ground truth. To publish in a context that does not permit redistributing these examples, delete the five `demo-*` files and replace the README references.
