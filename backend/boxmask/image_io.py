from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


def load_image(path: str | Path) -> Image.Image:
    """Load an image, bake EXIF orientation, and normalize to RGB.

    Raises FileNotFoundError or PIL errors; callers translate them into
    user-facing messages.
    """

    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise FileNotFoundError(f"图片不存在：{file_path}")
    image = Image.open(file_path)
    image.load()
    return ImageOps.exif_transpose(image).convert("RGB")


def image_size(path: str | Path) -> tuple[int, int]:
    with Image.open(Path(path).expanduser()) as image:
        return image.size
