# 打包 / Packaging

## 1. 构建前端

```bash
npm run build:web
```

输出 `apps/web/dist`，生产模式由 FastAPI `StaticFiles` 托管。

## 2. 构建 Python sidecar

```bash
.venv/Scripts/python.exe scripts/build_backend.py
```

PyInstaller spec：`backend/boxmask_backend.spec`。

- onedir、`console=False`；
- 日志重定向到 `userData/logs/backend.log`；
- 端口 0 + `ready.json`；
- 不打包 timm/torchvision（vendored `timm_compat.py`）；
- 输出 `backend/dist/boxmask-backend/boxmask-backend.exe`。

首次启动 PyTorch 导入较慢（几秒），Electron 会等待 `ready.json` 后再开窗。

## 3. 构建 Windows 安装包

```bash
npm run dist
```

Electron-builder 配置：`apps/desktop/electron-builder.yml`。

- 产品名：炽智 SegMentor
- appId：`com.chizhi.segmentor`
- 图标：`apps/desktop/build/icon.ico`
- extraResources：
  - `apps/web/dist` → `web`
  - `models/*.pth` → `models`
  - `backend/dist/boxmask-backend` → `backend`
- 目标：NSIS 安装包 + portable
- 输出：
  - `release/Chizhi-SegMentor-Setup-0.1.0.exe`（约 305MB）
  - `release/Chizhi-SegMentor-0.1.0-portable.exe`（约 283MB）
  - `release/win-unpacked/ChizhiSegMentor.exe`（免安装目录）

> 当前模型权重不进入 git。正式发布时把 `models/boxmask_repvit_best_snapshot.pth` 放到 `models/` 再执行 `npm run dist`，或发布一个**不含权重**的安装包，让用户首次启动选择 checkpoint（应用已支持）。

## 4. 模型分发

- 权重作为 GitHub Release 附件，附 SHA256。
- `scripts/verify_model.py` 可校验/下载。
- 模型卡见 `models/MODEL_CARD.md`。

## 5. 签名与 SmartScreen

- 未签名的 Windows 安装包会触发 SmartScreen；README/Release 说明“更多信息 → 仍要运行”。
- 后续可配置代码签名证书；electron-builder 支持 `CSC_LINK` / `CSC_KEY_PASSWORD`。
- 自动更新（electron-updater）需要签名 + Release 源，暂未启用。

## 6. CI

`.github/workflows/ci.yml`：测试 + 前端构建。

`.github/workflows/release.yml`：手动触发，构建 sidecar 与 Windows 安装包，上传 artifacts。CI 不包含模型权重，因此安装包默认不含权重；需要时用带权重的本地构建。

## 7. 体积参考

- CPU PyTorch + onedir sidecar：约 700MB–1GB（未压缩）
- NSIS 压缩后：约 300–500MB
- Electron 壳约 150–250MB
- 模型 39.8MB（可选）

体积主要来自 PyTorch；后续可尝试 ONNX Runtime 或分离模型运行时。
