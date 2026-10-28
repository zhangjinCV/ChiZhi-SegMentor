"""Short-lived signed URLs for local image/mask files."""

from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path
from urllib.parse import quote


def normalize_path(path: str | Path) -> str:
    return str(Path(path).expanduser())


def sign_path(token: str, path: str, expires: int) -> str:
    message = f"{path}|{expires}".encode()
    return hmac.new(token.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_signature(token: str, path: str, expires: int, signature: str) -> bool:
    if expires < int(time.time()):
        return False
    expected = sign_path(token, normalize_path(path), expires)
    return hmac.compare_digest(expected, signature)


def make_signed_url(token: str, path: str | Path, ttl: int = 3600) -> tuple[str, int]:
    normalized = normalize_path(path)
    expires = int(time.time()) + max(60, min(int(ttl), 86400))
    signature = sign_path(token, normalized, expires)
    url = f"/api/file?path={quote(normalized)}&expires={expires}&sig={signature}"
    return url, expires


def signed_file_url(token: str, path: str | Path, ttl: int = 3600) -> str:
    return make_signed_url(token, path, ttl)[0]
