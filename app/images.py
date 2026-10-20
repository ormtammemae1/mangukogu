"""Save uploaded game photos: fix phone rotation, shrink, and make a thumbnail.

Photos go to Vercel Blob when BLOB_READ_WRITE_TOKEN is set (hosting on Vercel), otherwise to a local
folder (laptop, Pi). The game stores either the local file name or, for Blob, the full photo URL; the
thumbnail always sits next to the photo as "thumb-" + its file name.
"""
import io
import os
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

FULL_SIZE = 1600
THUMB_SIZE = 480
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
BLOB_ENABLED = bool(os.getenv("BLOB_READ_WRITE_TOKEN"))


class BadImage(ValueError):
    pass


def _jpeg(img: Image.Image, size: int, quality: int) -> bytes:
    img = img.copy()
    img.thumbnail((size, size))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def save_image(data: bytes, image_dir: Path) -> str:
    """Store the photo and its thumbnail; return what the game should keep in `image`."""
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
    full = _jpeg(img, FULL_SIZE, 85)
    thumb = _jpeg(img, THUMB_SIZE, 80)
    if BLOB_ENABLED:
        from vercel.blob.sync import put_blob

        # Names are random and never reused, so browsers can cache them for good.
        options = dict(access="public", content_type="image/jpeg", cache_control_max_age=31536000)
        put_blob(f"thumb-{name}", thumb, **options)
        return put_blob(name, full, **options).url
    (image_dir / name).write_bytes(full)
    (image_dir / f"thumb-{name}").write_bytes(thumb)
    return name


def _is_url(image: str) -> bool:
    return image.startswith(("https://", "http://"))


def image_urls(image: str | None) -> tuple[str | None, str | None]:
    """The (photo, thumbnail) URLs for a game's stored `image`."""
    if not image:
        return None, None
    if _is_url(image):
        base, name = image.rsplit("/", 1)
        return image, f"{base}/thumb-{name}"
    return f"/images/{image}", f"/images/thumb-{image}"


def delete_image(image: str | None, image_dir: Path) -> None:
    if not image:
        return
    if _is_url(image):
        from vercel.blob.sync import delete_blob

        delete_blob(list(image_urls(image)))
        return
    for file in (image_dir / image, image_dir / f"thumb-{image}"):
        file.unlink(missing_ok=True)
