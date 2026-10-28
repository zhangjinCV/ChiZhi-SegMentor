# Third-party notices

Chizhi SegMentor includes or depends on the following open-source projects. Keep
this file and the referenced license texts when redistributing binaries.

| Project | Use | License |
|---|---|---|
| RepViT (`libs/RepViT`) | backbone architecture and model code, vendored under `backend/boxmask/vendor/` | Apache-2.0 (see `backend/boxmask/vendor/REPVIT_LICENSE`) |
| PyTorch | inference runtime | BSD-3-Clause |
| timm | reference for vendored `vendor/timm_compat.py` (SqueezeExcite / trunc_normal / register_model); dev-only for parity | Apache-2.0 |
| torchvision | dev-only dependency of timm for `scripts/parity_check.py` | BSD-3-Clause |
| FastAPI / Uvicorn / Pydantic | local API server | MIT / BSD / MIT |
| Pillow | image I/O | HPND |
| NumPy | array operations | BSD-3-Clause |
| OpenCV (headless) | mask morphology/contours | Apache-2.0 |
| Electron | desktop shell | MIT |
| React / React DOM | UI | MIT |
| Konva / react-konva | canvas | MIT |
| Vite / Tailwind CSS / lucide-react / zustand / sonner | frontend tooling and UI | MIT / MIT / ISC / MIT / MIT |

The model checkpoint is distributed separately and is covered by
`models/MODEL_CARD.md`, not by the source-code license.
