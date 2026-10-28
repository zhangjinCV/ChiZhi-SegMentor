"""Runtime settings shared by the API server and the desktop sidecar launcher."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _default_data_dir() -> Path:
    root = os.getenv("LOCALAPPDATA")
    if root:
        return Path(root) / "ChizhiSegMentor"
    return Path.home() / ".chizhi-segmentor"


@dataclass
class RuntimeSettings:
    data_dir: Path = field(default_factory=_default_data_dir)
    model_path: Path = field(
        default_factory=lambda: REPO_ROOT / "models" / "boxmask_repvit_best_snapshot.pth"
    )
    device: str = "auto"
    host: str = "127.0.0.1"
    port: int = 0
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    ready_file: Path | None = None
    web_dist: Path | None = None
    dev_mode: bool = False
    log_file: Path | None = None

    @classmethod
    def from_env(cls) -> RuntimeSettings:
        data_dir = Path(os.getenv("BOXMASK_DATA_DIR", _default_data_dir())).expanduser()
        ready = os.getenv("BOXMASK_READY_FILE")
        web = os.getenv("BOXMASK_WEB_DIST")
        log = os.getenv("BOXMASK_LOG_FILE")
        settings = cls(
            data_dir=data_dir,
            model_path=Path(
                os.getenv("BOXMASK_MODEL", REPO_ROOT / "models" / "boxmask_repvit_best_snapshot.pth")
            ).expanduser(),
            device=os.getenv("BOXMASK_DEVICE", "auto"),
            host=os.getenv("BOXMASK_HOST", "127.0.0.1"),
            port=int(os.getenv("BOXMASK_PORT", "0")),
            token=os.getenv("BOXMASK_TOKEN", secrets.token_urlsafe(32)),
            ready_file=Path(ready).expanduser() if ready else data_dir / "runtime" / "ready.json",
            web_dist=Path(web).expanduser() if web else REPO_ROOT / "apps" / "web" / "dist",
            dev_mode=_env_bool("BOXMASK_DEV", False),
            log_file=Path(log).expanduser() if log else data_dir / "logs" / "backend.log",
        )
        settings.ensure_dirs()
        return settings

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.ready_file is not None:
            self.ready_file.parent.mkdir(parents=True, exist_ok=True)
        if self.log_file is not None:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
