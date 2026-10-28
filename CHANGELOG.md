# Changelog

## Unreleased

### 文档

- README 拆分为中文 `README.md` + 英文 `README.en.md`，顶部可互相切换。
- 新增真实模型输出 demo：3 场景 hero GIF、真实应用操作 GIF、6 组伪装/多目标前后对比、4 组 DUTS-TR 通用目标、火烈鸟一框多目标 GIF。
- 新增 [示例图片来源与许可说明](docs/images/DATASETS.md)（NBCM/COD10K、DUTS-TR、Pixabay）。
- 模型卡补充训练数据组成、demo 抽样统计与示例图片许可边界。
- README 增加 ECCV 2024 论文引用（Zhang et al., Learning Camouflaged Object Detection from Noisy Pseudo Label）。

## 0.1.0 — 2026-10-28

首个可运行版本（M1 单图 + M2 批量基础版）。

### 单图

- Electron + React + Konva 桌面壳，FastAPI sidecar，Windows 生产模式。
- 图片导入（文件/拖拽/多选）、中文路径、EXIF 方向。
- 画框、移动、缩放、数值坐标、多框、撤销/重做、复制。
- 自动分割、阈值/padding/最大连通域/填洞/平滑。
- mask 叠加/原图、透明度、面积/平均概率/耗时、mask 下载/复制。
- 模型输入双分支预览、模型加载/切换/设备选择、SHA256 展示。
- 会话恢复（localStorage）、主题、快捷键、帮助。

### 批量

- VOC XML / COCO JSON / LabelMe JSON / YOLO txt / CSV/JSON 解析。
- 图片-标注配对预览、缺失/空标注提示、类别过滤、跳过无框图。
- 单 worker 任务队列、进度、暂停/恢复/取消、失败重试、job.json 清单。
- 结果网格、mask 叠加详情、任务历史。
- PNG / overlay / COCO / LabelMe / CSV 导出。

### 模型/工程

- 权重快照冻结 + SHA256。
- 6 通道预处理与 raw logits 逐 bit 一致（parity `max_abs=0.0`）。
- vendored RepViT + 最小 timm 兼容层，运行时无 timm/torchvision。
- PyInstaller sidecar、electron-builder 配置、品牌 logo/图标。
- 21 项后端测试、真实单图/批量 API 冒烟、Electron UI 冒烟。
- 真实 `tank_annotated` 252 张全量批量：252/252 完成、0 失败、CPU 约 1.04 img/s。
- 打包后的 sidecar 与打包后的单图/批量 UI/导出冒烟通过；Windows NSIS/portable 构建成功。

### 已知限制

- 项目 SQLite/项目页、中英双语、代码签名、自动更新尚未实现。
- Windows NSIS/portable 安装包已在本地构建验证；未签名，SmartScreen 会提示。
- 单图结果不持久化（刷新后需重新分割；框/图片路径保留）。
- 批量任务在应用重启后标记为 interrupted，可继续；正在处理的单张会重置。
- 未做 CUDA 安装包验收；CPU 版不支持 CUDA。
- 模型指标来自 GT 框验证，手绘框鲁棒性需独立评测。
