"""PyInstaller entry point for the FastAPI sidecar."""

import multiprocessing

from boxmask.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
