# 架构 / Architecture

## 进程结构

```text
Electron main
  ├─ 单实例锁 / 原生文件对话框 / 日志 / 退出清理
  ├─ spawn Python sidecar
  │    ├─ 绑定 127.0.0.1:0
  │    ├─ ready.json {pid, port, token} 原子写入 userData/runtime/
  │    └─ FastAPI (Uvicorn, 单 worker)
  │         ├─ /api/* 需要 Bearer token（/api/health 与签名文件 URL 例外）
  │         ├─ 静态前端（生产模式）
  │         ├─ 单图同步推理
  │         └─ 批量任务线程 + JSON manifest
  └─ BrowserWindow (React + Konva)
       └─ preload contextBridge: apiBase / token / 原生对话框 / webUtils 路径
```

开发模式下 Electron 加载 Vite `http://127.0.0.1:5173`；生产模式加载 sidecar 的 `http://127.0.0.1:<port>/`，由 FastAPI 托管 `apps/web/dist`。

## 模型契约（不可随意更改）

- 架构：RepViT-M1.1 + PNet，10.33M 参数；vendored 在 `backend/boxmask/vendor/`。
- 输入：`6×512×768` float32
  - 通道 0–2：RGB 直接拉伸到 768×512（不保持比例、不 pad）
  - 通道 3–5：框裁剪后 letterbox 到 768×512（黑色 0 填充）
  - 归一化：`/255` 后 6 通道统一 ImageNet mean/std
- 框：原图像素坐标，PIL bbox `(x0,y0,x1,y1)`，右/下开区间；越界 clamp；宽/高 <2px 回退整图。
- 输出：`net(x)[4]`，sigmoid + 0.5 阈值；概率图 bilinear 回原图尺寸后阈值化。
- 一致性基线：`scripts/parity_check.py` 对比 6 通道输入与 512×768 raw logits，当前 `max_abs=0.0`。
- 运行时不再依赖 timm/torchvision：`vendor/timm_compat.py` 只实现 SqueezeExcite / trunc_normal_ / register_model。

## 后端模块

| 模块 | 作用 |
|---|---|
| `boxmask/api/app.py` | FastAPI 路由、鉴权、模型管理、批量端点、静态前端 |
| `boxmask/inference/predictor.py` | 预处理、6 通道构造、推理、回映射 |
| `boxmask/inference/mask_utils.py` | 阈值后处理、mask PNG、轮廓、overlay/cutout |
| `boxmask/annotations/` | VOC / COCO / LabelMe / YOLO / CSV-JSON 适配器 |
| `boxmask/batch/manager.py` | 单 worker 任务队列、暂停/恢复/取消/重试、manifest |
| `boxmask/batch/export.py` | mask/overlay/COCO/LabelMe/CSV 导出 |
| `boxmask/security.py` | 短时签名文件 URL |
| `boxmask/settings.py` | 数据目录、模型路径、设备、token、ready file |
| `boxmask/cli.py` | sidecar 入口：端口 0、日志重定向、ready.json、退出清理 |
| `boxmask/image_io.py` | EXIF 烘焙 + RGB 归一化读图 |

## 数据目录

```text
%APPDATA%/ChizhiSegMentor/              # Electron userData（可用 BOXMASK_USER_DATA 覆盖）
├─ runtime/ready.json                   # sidecar 端口/token
├─ logs/backend.log, desktop.log
├─ uploads/                             # 浏览器开发模式临时上传
└─ batch/<job_id>/
   ├─ job.json                          # 任务清单（图片/框/结果路径）
   ├─ masks/<index>_<stem>/box_XX.png
   ├─ overlays/<index>_<stem>_box_XX.png
   └─ export/                           # 默认导出目录
```

单图会话（图片路径、框、参数）存在 Chromium localStorage `boxmask.session.v1`；批量任务用 `job.json` 持久化，应用重启后可在任务历史中恢复/继续。SQLite 项目库尚未实现（计划中）。

## 安全

- sidecar 只绑定 `127.0.0.1`，端口由 Python 绑定 `:0` 获取，避免 TOCTOU。
- 静态 assets 免鉴权；`/api/*` 需要 `Authorization: Bearer <token>`；`/api/file` 用短时 HMAC 签名 URL（图片 `<img>` 不能带 header）。
- Renderer：`contextIsolation=true`、`nodeIntegration=false`；文件读写经后端或白名单 IPC。
- 运行时无遥测、无云端上传；只有用户主动下载模型时才访问 GitHub Release。

## 批量流程

1. `POST /api/batch/parse` 解析标注，返回前 300 条预览与统计。
2. `POST /api/batch/run` 重新解析全部记录，创建 `BatchJob`，启动单 worker 线程。
3. worker 每图只解码/整图 resize 一次，多框合批推理；每图完成即写 mask/overlay 与 `job.json`。
4. 前端轮询 `GET /api/batch/jobs/{id}`；暂停/恢复/取消/重试通过 POST 控制端点。
5. `POST /api/batch/jobs/{id}/export` 复制/生成导出文件。

瓶颈在 PyTorch CPU 推理；默认单 worker，交互单图请求与批量共享 `ModelManager` 的推理锁，交互会插到批量图片之间。
