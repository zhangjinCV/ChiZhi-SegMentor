# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Chizhi SegMentor FastAPI sidecar.

Build from the repo root:
    pyinstaller backend/boxmask_backend.spec --noconfirm --clean \
        --distpath backend/dist --workpath backend/build
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
ENTRY = ROOT / "scripts" / "backend_entry.py"
ICON = ROOT / "apps" / "desktop" / "build" / "icon.ico"

hiddenimports = collect_submodules("uvicorn") + [
    "boxmask.api.app",
    "boxmask.cli",
    "boxmask.batch.manager",
    "boxmask.annotations.coco",
    "boxmask.annotations.csv_json",
    "boxmask.annotations.labelme",
    "boxmask.annotations.voc",
    "boxmask.annotations.yolo",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.lifespan.on",
]

datas = [
    (str(ROOT / "backend" / "boxmask" / "vendor" / "REPVIT_LICENSE"), "boxmask/vendor"),
]

excludes = [
    "timm",
    "torchvision",
    "tensorboard",
    "matplotlib",
    "pandas",
    "scipy",
    "IPython",
    "pytest",
    "tkinter",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
]

a = Analysis(
    [str(ENTRY)],
    pathex=[str(ROOT / "backend")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="boxmask-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ICON) if ICON.is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="boxmask-backend",
)
