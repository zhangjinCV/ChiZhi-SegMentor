#!/usr/bin/env python3
"""Verify (and optionally download) the frozen Chizhi SegMentor checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_PATH = REPO / "models" / "boxmask_repvit_best_snapshot.pth"
DEFAULT_SHA256 = "17b8f2d5fc0e65b1d6ec1b0c8ec123452fba02e4ba4dc784c95d4ed288f82d4c"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"downloading {url}")
    with urllib.request.urlopen(url) as response, tmp.open("wb") as handle:
        total = int(response.headers.get("Content-Length") or 0)
        received = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            received += len(chunk)
            if total:
                print(f"\r  {received / total * 100:5.1f}%  {received / 1024 / 1024:.1f} MiB", end="")
        print()
    os.replace(tmp, dest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--sha256", default=DEFAULT_SHA256)
    parser.add_argument("--url", default=None, help="optional download URL")
    args = parser.parse_args()

    path: Path = args.path.expanduser()
    if args.url:
        download(args.url, path)

    if not path.is_file():
        print(f"checkpoint not found: {path}", file=sys.stderr)
        print("pass --url or download the release asset manually.", file=sys.stderr)
        return 2

    actual = sha256_file(path)
    size = path.stat().st_size
    print(f"file:   {path}")
    print(f"size:   {size:,} bytes")
    print(f"sha256: {actual}")
    if args.sha256 and actual.lower() != args.sha256.lower():
        print("MODEL CHECK FAILED: sha256 mismatch", file=sys.stderr)
        return 1
    print("MODEL CHECK PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
