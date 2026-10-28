<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/chizhi-lockup-dark.png">
    <img src="docs/assets/chizhi-lockup-light.png" alt="CHIZHI LAB" width="520">
  </picture>
</p>

# Chizhi SegMentor · Box-Prompted Segmentation Workbench

<p align="center"><a href="README.md">简体中文</a> · <strong>English</strong></p>

**CHIZHI LAB**

![status](https://img.shields.io/badge/status-M2%20beta-orange)
![license](https://img.shields.io/badge/license-Apache--2.0-blue)
![platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D4)
![python](https://img.shields.io/badge/python-3.12-3776AB)

Chizhi SegMentor is a local-first desktop tool for box-prompted segmentation. Import an image, draw a box on the canvas, and the model returns a foreground mask. The backend is FastAPI/PyTorch; the desktop shell is Electron with a React + Konva canvas. Images and inference stay on your machine — no uploads, no telemetry.

The app UI is currently Chinese; UI i18n is planned. The repository currently ships the **M1 single-image workspace and M2 batch beta**: model inference, box drawing, mask overlays, threshold/post-processing, session restore, plus VOC/COCO/LabelMe/YOLO/CSV batch import, a task queue with pause/resume/retry, and COCO/LabelMe/CSV export. A PyInstaller sidecar and Windows NSIS/portable installers have also been built and smoke-tested. Project SQLite, code signing, and auto-update are planned next.

<p align="center">
  <img src="docs/images/demo-hero.gif" width="920" alt="Animated demo from box prompt to foreground mask">
</p>

<p align="center"><sub>Box prompt → foreground mask · Butterfly / Seahorse / Lizard · real model output (animation pacing is illustrative, not real-time speed)</sub></p>

## Demos

### Single image: draw a box, get a mask

Recorded from the real Electron app — not a mock: import → drag a box → automatic inference → toggle overlay/original. The example is a 400×258 two-bird image: one box per prairie chicken, each inferred separately; CPU inference is about 0.6 s per box.

<p align="center">
  <img src="docs/images/demo-ui.gif" width="920" alt="Chizhi SegMentor single-image workspace in action">
</p>

### Camouflaged and multi-object examples

Top row: original image + box. Bottom row: model mask overlay and contour. Examples from NBCM/COD10K and DUTS-TR (the two birds); all masks are real model output with no manual retouching.

<p align="center">
  <img src="docs/images/demo-grid.jpg" width="920" alt="Before/after box-prompted segmentation of two birds, snake, cicada, batfish, grasshopper and butterfly">
</p>

### Multi-object: one box, several birds

One box covers three flamingos, and the model still returns three separate masks. This is a deliberate multi-object stress test; for precise work, prefer one box per object.

<p align="center">
  <img src="docs/images/demo-flamingo.gif" width="920" alt="Animated segmentation of three flamingos inside one box">
</p>

### General objects

The model is not limited to camouflage. DUTS-TR examples — apple, corgi, parrot, car:

<p align="center">
  <img src="docs/images/demo-general.jpg" width="920" alt="DUTS-TR general object segmentation examples">
</p>

> Demo images remain under the terms of the NBCM/COD10K and DUTS-TR datasets and the Pixabay image bank and are **not** licensed under Apache-2.0; the project author has confirmed they may be used for this public demo repository. See [docs/images/DATASETS.md](docs/images/DATASETS.md) for sources and replacement instructions; follow the original dataset/image-bank terms for any further redistribution.

## Features (current)

**Single-image workspace**

- Import images (file picker, folder/image drag-and-drop, multi-select); Unicode paths and EXIF orientation handled.
- Draw, move and resize boxes; numeric coordinates; multiple boxes; undo/redo; auto-segment on box creation.
- Toggle mask overlay/original, opacity slider, mask area/mean probability/latency.
- Threshold, box padding, largest connected component, hole filling, smoothing.
- Model-input preview: side-by-side stretched full image and letterboxed box crop.
- Model load/switch, device selection, SHA256 display; local FastAPI sidecar with a session token.
- Session restore (image path, boxes, parameters); masks need re-running after reload.

**Batch workspace**

- Auto-detect Pascal VOC XML, COCO JSON, LabelMe JSON, YOLO txt, and CSV/generic JSON coordinates.
- Image-annotation pairing preview, missing-image/empty-annotation warnings, class filtering, skip-empty option.
- Batch queue, live progress, pause/resume/cancel, retry failures, persistent job manifests.
- Result grid and mask overlay detail; export PNG / overlay / COCO instance segmentation / LabelMe polygon / CSV.
- Job history; interrupted jobs can be resumed after restarting the app.

Planned: UI i18n, project SQLite/project page, code signing and auto-update, CLI, mask brush (v1.1), SSE progress.

## Interface

Single-image workspace: image list on the left, Konva canvas in the center, box/parameter/result inspector on the right.

![Single-image workspace](docs/images/single-workspace.jpg)

Batch workspace: a three-step wizard (import & pair → parameters → run & results), with a result grid and multi-format export.

![Batch import](docs/images/batch-import.jpg)
![Batch results](docs/images/batch-workspace.jpg)

## Model

Default checkpoint:

```text
models/boxmask_repvit_best_snapshot.pth
```

- Architecture: RepViT-M1.1 + PNet decoder, ≈10.33M parameters.
- Training data: SA-1B + pnet_data (COD / SOD / DIS, excluding COCONUT); class-agnostic foreground segmentation.
- Input: fixed `6 × 512 × 768` (first 3 channels = stretched full image; last 3 = letterboxed box crop).
- Output: `net(x)[4]`, a single-channel logit map; sigmoid + 0.5 threshold; probabilities are bilinearly upsampled to the original size before export.
- This snapshot comes from `model6ch/runs/repvit_pnet/best.pth` (epoch 30; validation MAE 0.02517 / IoU 0.83954; validation boxes are GT-mask bounding boxes).
- SHA256: `17b8f2d5fc0e65b1d6ec1b0c8ec123452fba02e4ba4dc784c95d4ed288f82d4c`
- Weights are not committed to git; public releases distribute them as GitHub Release assets or via a download script. See [models/MODEL_CARD.md](models/MODEL_CARD.md).

> The model performs **binary foreground segmentation inside the box**. Labels are only for organization and export; one box should contain roughly one object.

Model-input preview (stretched full-image branch + letterboxed box-crop branch):

![Model input preview](docs/images/model-input-preview.jpg)

## Validation status (2026-10-28)

- 6-channel input + 512×768 raw logits match the training repository bit-for-bit: `max_abs=0.0`.
- Backend tests: 21 total (17 without external data; 4 real-dataset tests run when `BOXMASK_TANK_DATA` / `BOXMASK_TANK_SELECTED` are set).
- Full real `tank_annotated` batch: 252/252 images, 0 failures, ≈`1.04 img/s` on CPU (≈242 s).
- Packaged sidecar, packaged single-image/batch UI, and COCO/LabelMe/CSV exports passed smoke tests.
- Windows NSIS 305 MB / portable 283 MB installers were built locally; unsigned and not yet tested on a clean machine.
- Demo boxes are mostly GT-mask/object bounding boxes expanded by about 2–3%; the flamingo box is a hand-drawn multi-object box. They are for illustration only; hand-drawn box robustness still needs a separate evaluation.

## Quick start (development)

Requirements: Windows 10/11, Python 3.12, Node.js 22+, npm.

```bash
# 1) Python environment (uv downloads Python 3.12 automatically)
pip install --user uv
uv sync --extra dev

# 2) Frontend dependencies
npm install

# 3) Browser dev mode: API 8765 + Vite 5173
npm run dev
# open http://127.0.0.1:5173

# 4) Electron dev mode: Electron starts the Python sidecar + Vite
npm run dev:desktop

# 5) Production preview: build the web app; FastAPI serves it and Electron loads the local port
npm run preview
```

If the model is not loaded on first launch, choose a checkpoint in Settings (top right) or click “Load default model” in the inspector.

## Windows installers

```bash
npm run build:web
.venv/Scripts/python.exe scripts/build_backend.py
npm run dist
```

Artifacts in `release/`:

- `Chizhi-SegMentor-Setup-0.1.0.exe` (NSIS, ≈305 MB)
- `Chizhi-SegMentor-0.1.0-portable.exe` (portable)
- `win-unpacked/ChizhiSegMentor.exe` (unpacked directory)

The local build includes the frozen 39.8 MB checkpoint; an open-source release can also ship without weights so users choose a checkpoint on first launch. The installers are unsigned, so Windows SmartScreen will warn. See [docs/packaging.md](docs/packaging.md).

## Repository layout

```text
apps/web/                 React + Konva frontend
apps/desktop/             Electron main / preload
backend/boxmask/          FastAPI, inference, mask utilities
backend/boxmask/vendor/   vendored RepViT/RepViTPNet inference code
models/                   checkpoint snapshot + model card (weights not in git)
scripts/                  parity_check.py and other dev scripts
docs/                     architecture, formats, FAQ, demo images
```

## Numerical parity

M0 requires the forward pass to match the training repository. Run:

```bash
.venv/Scripts/python.exe scripts/parity_check.py
```

The script compares the preprocessed 6-channel tensor and 512×768 raw logits for one real image + VOC box, and writes golden `.npy` files under `backend/tests/fixtures/`.

## Documentation

The detailed docs are currently in Chinese.

- [Architecture and data flow](docs/architecture.md)
- [Annotation formats](docs/annotation-formats.md)
- [Development guide](docs/development.md)
- [Packaging and model distribution](docs/packaging.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Brand assets and trademarks](docs/assets/README.md)
- [Demo image credits](docs/images/DATASETS.md)

## Citation

The 6-channel box-prompted segmentation model and training approach in this project build on:

**Jin Zhang, Ruiheng Zhang, Yanjiao Shi, Zhe Cao, Nian Liu, Fahad Shahbaz Khan. “Learning Camouflaged Object Detection from Noisy Pseudo Label.” ECCV 2024, pp. 158–174.**  
DOI: [10.1007/978-3-031-73232-4_9](https://doi.org/10.1007/978-3-031-73232-4_9)

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

## Branding

Chizhi SegMentor is developed by **CHIZHI LAB**. The lab logo, names and lockups are trademarks of CHIZHI LAB and are **not** licensed under Apache-2.0. When redistributing or forking, please keep the lab lockup and attribution at the top of the README. See [docs/assets/README.md](docs/assets/README.md).

## Privacy and license

- Images, masks, and the model stay on the machine; there are no network requests at runtime (the only network access is a user-initiated model download).
- Code is Apache-2.0 — see [LICENSE](LICENSE). Vendored RepViT is also Apache-2.0 — see [backend/boxmask/vendor/REPVIT_LICENSE](backend/boxmask/vendor/REPVIT_LICENSE).
- Model and training-data terms are described in the model card; README demo images are covered in [docs/images/DATASETS.md](docs/images/DATASETS.md). Confirm both before a public release.

<p align="center"><sub>CHIZHI LAB · Chizhi SegMentor</sub></p>
