#!/usr/bin/env python3
"""Build the Python sidecar with PyInstaller (onedir)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(ROOT / "backend" / "boxmask_backend.spec"),
        "--noconfirm",
        "--clean",
        "--distpath",
        str(ROOT / "backend" / "dist"),
        "--workpath",
        str(ROOT / "backend" / "build"),
    ]
    print(" ".join(command))
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
