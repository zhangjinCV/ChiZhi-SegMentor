# 常见问题 / Troubleshooting

## 模型未加载

- 确认 `models/boxmask_repvit_best_snapshot.pth` 存在，或右上角设置中选择任意 RepViTPNet checkpoint。
- 校验 SHA256：

```bash
python scripts/verify_model.py
```

- 权重是裸 `state_dict`（约 39.8MB）；不是训练时的 `{'model': ...}` 外壳。

## CPU 很慢

- 这是正常的：1920×1080 单框在常见笔记本 CPU 上约 0.5–1.2 秒。
- 批量默认串行；不要开多个应用实例同时跑批量（单实例锁会阻止，但同机多开脚本不受限）。
- CUDA 版需要单独打包 CUDA 版 PyTorch；CPU 安装包选择 `cuda` 会报错。

## mask 为空 / 效果差

- 一个框尽量只框一个目标；框内多目标会合并。
- 框越贴近目标通常越好；可尝试增大框、降低阈值。
- 验证集指标使用的是 GT mask 外接框，手绘框效果需自行评估。
- 检查“模型输入预览”：整图分支应拉伸到 768×512，框分支应有黑色 letterbox。

## 中文路径/图片读不了

- 读图统一走 Pillow，支持中文路径。
- 若仍失败，确认图片不是损坏文件、没有超长路径（Windows 260 字符限制）。

## 批量解析失败

- VOC：确认 XML 的 `<filename>` 与图片目录中的文件名一致。
- COCO：确认 JSON 有 `images` + `annotations`。
- LabelMe：确认 JSON 有 `shapes`。
- YOLO：必须提供图片文件夹；类别名从 `classes.txt`/`data.yaml` 读取。
- CSV：确认图片列与坐标列；`manifest.csv` 选 1920 坐标列，图片目录选 `JPEGImages`。
- 空标注默认跳过；如果全部跳过，任务会提示“没有可处理的图片”。

## 批量任务中断

- 任务清单在 `%APPDATA%/ChizhiSegMentor/batch/<job_id>/job.json`。
- 应用重启后任务状态会变为 `interrupted`；在批量页任务历史中选择并点“继续”。
- 已完成项不会重复推理；失败项可“重试失败”。

## 签名图片 URL 过期

- 单图/批量结果图片使用 1 小时短时签名 URL；长时间打开后图片可能加载失败。
- 重新打开/刷新任务即可重新签名。

## Electron 变成 Node / 无法启动

如果 shell 里全局设置了 `ELECTRON_RUN_AS_NODE=1`，Electron 会以 Node 模式运行。项目脚本已经通过 `scripts/electron.cjs` 清除该变量；手动运行 Electron 时请确保未设置。

## 日志

- `%APPDATA%/ChizhiSegMentor/logs/desktop.log`
- `%APPDATA%/ChizhiSegMentor/logs/backend.log`

设置页/帮助菜单可打开日志目录（Electron IPC）。
