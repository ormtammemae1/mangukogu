"""Save uploaded game photos: fix phone rotation, shrink, and make a thumbnail."""
import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

FULL_SIZE = 1600
THUMB_SIZE = 480
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class BadImage(ValueError):
    pass


def save_image(data: bytes, image_dir: Path) -> str:
    """Store the photo and its thumbnail; return the file name."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise BadImage("too large")
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
    except (UnidentifiedImageError, OSError) as e:
        raise BadImage(str(e)) from e
    if img.mode not in ("RGB", "L"):
        background = Image.new("RGB", img.size, "white")
        img = img.convert("RGBA")
        background.paste(img, mask=img.getchannel("A"))
        img = background

    name = f"{uuid.uuid4().hex}.jpg"
    full = img.copy()
    full.thumbnail((FULL_SIZE, FULL_SIZE))
    full.save(image_dir / name, "JPEG", quality=85, optimize=True)
    thumb = img.copy()
    thumb.thumbnail((THUMB_SIZE, THUMB_SIZE))
    thumb.save(image_dir / f"thumb-{name}", "JPEG", quality=80, optimize=True)
    return name


def delete_image(name: str | None, image_dir: Path) -> None:
    if not name:
        return
    for file in (image_dir / name, image_dir / f"thumb-{name}"):
        file.unlink(missing_ok=True)
