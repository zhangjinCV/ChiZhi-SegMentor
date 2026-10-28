"""Entry point for the packaged FastAPI sidecar.

The desktop shell starts this module as a windowed PyInstaller executable.  In
that mode ``sys.stdout``/``sys.stderr`` are ``None``, so logging is redirected to
a file and readiness is communicated through an atomically-written JSON file
instead of stdout.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import multiprocessing
import os
import sys
import time
from pathlib import Path

import uvicorn

from . import __version__
from .api.app import create_app
from .settings import RuntimeSettings

_log_handles: list = []


def _redirect_stdio(log_file: Path | None) -> Path | None:
    if log_file is None:
        return None
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None:
        handle = open(log_file, "a", encoding="utf-8", buffering=1)
        sys.stdout = handle
        _log_handles.append(handle)
    if sys.stderr is None:
        handle = open(log_file, "a", encoding="utf-8", buffering=1)
        sys.stderr = handle
        _log_handles.append(handle)
    return log_file


def _configure_logging(log_file: Path | None) -> None:
    handlers: list[logging.Handler] = []
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def _write_ready(settings: RuntimeSettings, port: int) -> None:
    if settings.ready_file is None:
        return
    payload = {
        "pid": os.getpid(),
        "port": port,
        "token": settings.token,
        "started_at": time.time(),
        "version": __version__,
    }
    settings.ready_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = settings.ready_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, settings.ready_file)


def _remove_ready(settings: RuntimeSettings) -> None:
    if settings.ready_file is None:
        return
    try:
        settings.ready_file.unlink()
    except OSError:
        pass


async def _serve(server: uvicorn.Server, settings: RuntimeSettings) -> None:
    task = asyncio.create_task(server.serve())
    try:
        while not server.started:
            if task.done():
                await task
                return
            await asyncio.sleep(0.05)
        sock = server.servers[0].sockets[0]
        port = int(sock.getsockname()[1])
        _write_ready(settings, port)
        logging.getLogger("boxmask").info(
            "Chizhi SegMentor backend ready on http://%s:%s (pid=%s)",
            settings.host,
            port,
            os.getpid(),
        )
        await task
    finally:
        _remove_ready(settings)


def main(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()

    parser = argparse.ArgumentParser(description="Chizhi SegMentor backend sidecar")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args(argv)

    settings = RuntimeSettings.from_env()
    if args.host:
        settings.host = args.host
    if args.port is not None:
        settings.port = args.port
    if args.model:
        settings.model_path = Path(args.model).expanduser()
    if args.device:
        settings.device = args.device
    if args.dev:
        settings.dev_mode = True
    settings.ensure_dirs()

    log_file = _redirect_stdio(settings.log_file)
    _configure_logging(log_file)

    app = create_app(settings)
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_config=None,
        log_level="info",
        workers=1,
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)
    try:
        asyncio.run(_serve(server, settings))
    except KeyboardInterrupt:
        pass
    finally:
        _remove_ready(settings)
        for handle in _log_handles:
            try:
                handle.close()
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
