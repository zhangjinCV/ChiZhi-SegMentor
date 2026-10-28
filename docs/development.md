# 开发 / Development

## 环境

- Windows 10/11（当前主要开发平台；代码保持跨平台）
- Python 3.12
- Node.js 22+ / npm
- 可选：NVIDIA GPU（CUDA 版 PyTorch 需单独环境）

## 首次安装

```bash
pip install --user uv
uv sync --extra dev
npm install
```

`uv sync` 使用 `pyproject.toml` 中的 PyTorch CPU 索引；若网络较慢，可先配置镜像或使用已安装的 torch 环境。

模型权重放在：

```text
models/boxmask_repvit_best_snapshot.pth
```

## 开发模式

```bash
# 浏览器模式：API 8765（--dev，免 token）+ Vite 5173
npm run dev

# Electron 模式：Electron 自己拉起 sidecar（带 token）+ Vite
npm run dev:desktop

# 生产预览：构建前端后由 FastAPI 托管，Electron 加载本地端口
npm run preview
```

## 测试

```bash
.venv/Scripts/python.exe -m pytest -q
```

覆盖：

- 模型预处理/框 clamp/letterbox/mask 后处理（12 项）
- 标注适配器（VOC/COCO/LabelMe/YOLO/CSV/JSON，9 项）
- FastAPI 健康检查/鉴权/错误码

## 数值一致性

```bash
.venv/Scripts/python.exe scripts/parity_check.py
```

输出 `input_equal=true`、`logits_max_abs=0.0` 才算通过。任何改动预处理、checkpoint 或模型代码后都必须重跑。

## 冒烟脚本

```bash
# 真实单图 API：加载权重、分割 tank 样例、签名图片 URL
.venv/Scripts/python.exe scripts/smoke_api.py

# 批量 API：3 张真实图，VOC -> 任务 -> COCO/LabelMe/CSV 导出
.venv/Scripts/python.exe scripts/smoke_batch.py

# 批量控制：暂停/恢复/取消/失败重试
.venv/Scripts/python.exe scripts/smoke_batch_controls.py

# 全量真实数据：252 张 tank VOC（CPU 约 4 分钟）
.venv/Scripts/python.exe scripts/smoke_batch_full.py

# PyInstaller sidecar：独立 exe 启动 + 真实推理
.venv/Scripts/python.exe scripts/smoke_packaged.py

# Electron UI（需要 Vite 在 5173）：单图真实鼠标拉框、撤销/重做、预览、刷新恢复
node scripts/ui_smoke.cjs

# 批量 UI：3 张图导入 -> 解析 -> 运行 -> 导出
node scripts/ui_smoke_batch.cjs

# 同一批量 UI 流程跑在打包后的 exe 上
BOXMASK_PACKAGED=1 node scripts/ui_smoke_batch.cjs

# 打包后的 exe：空态 + 拖拽上传 + 画框 + mask
node scripts/ui_smoke_packaged.cjs

# 生产壳：开发 Electron 加载 FastAPI 静态产物（Vite 不需要）
node scripts/ui_smoke_prod.cjs
```

UI 冒烟依赖 Playwright 的 Electron 驱动（无需下载 Chromium）：

```bash
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install -D playwright
```

## 构建

```bash
# 前端
npm run build:web

# Python sidecar（PyInstaller onedir）
.venv/Scripts/python.exe scripts/build_backend.py

# Windows 安装包 + 便携版（需要先构建前端和 sidecar）
npm run dist
```

产物：

- `backend/dist/boxmask-backend/boxmask-backend.exe`
- `release/` 下的 NSIS 安装包与 portable exe

详见 [packaging.md](packaging.md)。

## 关键不变量

修改模型/预处理时必须保持：

1. 输入固定 `6×512×768`，整图拉伸 + 框裁剪 letterbox。
2. 框是原图像素 xyxy，右/下开；<2px 回退整图。
3. 输出取 `net(x)[4]`；sigmoid 后双线性回原图再阈值。
4. 默认 threshold=0.5、padding=0、后处理关闭。
5. `scripts/parity_check.py` 必须通过。

## 品牌

- 产品名：**炽智 SegMentor**。
- 实验室：**炽智实验室 CHIZHI LAB**。
- Logo 资源在 `docs/assets/` 与 `apps/web/public/`；应用图标在 `apps/desktop/build/`。
- Logo 与实验室名称不在 Apache-2.0 授权范围内，规则见 [assets/README.md](assets/README.md)。
