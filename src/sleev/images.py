"""Measure and re-encode cover images on disk."""

from __future__ import annotations

from io import BytesIO
import logging
from pathlib import Path

from PIL import Image

log = logging.getLogger(__name__)

# A cover smaller than this on either side isn't worth keeping.
MIN_COVER_PIXELS = 500


def dimensions(path: Path) -> tuple[int, int] | None:
    """Pixel size of the image at *path*, or None if it can't be read.

    Pillow only reads the header here, so this stays cheap on large files.
    """
    try:
        with Image.open(path) as image:
            return image.size
    except OSError:
        # Truncated, empty, or not actually an image. Callers treat that the
        # same as having no cover at all, so the folder gets a fresh download.
        return None


def png_bytes(source: Path) -> bytes:
    """Re-encode the image at *source* as PNG, without writing a file.

    A box set converts once and writes the result into every disc folder.
    """
    buffer = BytesIO()
    with Image.open(source) as image:
        _save_png(image, buffer)
    return buffer.getvalue()


def _save_png(image: Image.Image, destination: Path | BytesIO) -> None:
    # Drop a palette or CMYK profile for something PNG stores predictably,
    # keeping alpha where the original had it.
    mode = "RGBA" if "A" in image.getbands() else "RGB"
    image.convert(mode).save(destination, "PNG", optimize=True)


def to_png(source: Path, destination: Path) -> None:
    """Re-encode the file at *source* as a PNG at *destination*, removing *source*.

    A no-op when the two are the same file — there is nothing to convert and
    unlinking would destroy the cover.
    """
    if source == destination:
        return

    with Image.open(source) as image:
        _save_png(image, destination)

    source.unlink()


def data_to_png_bytes(data: bytes) -> bytes:
    """Re-encode freshly downloaded image *data* as PNG."""
    buffer = BytesIO()
    with Image.open(BytesIO(data)) as image:
        _save_png(image, buffer)
    return buffer.getvalue()


def to_icns(source: Path, destination: Path) -> None:
    """Write the image at *source* as a macOS icon at *destination*.

    The art is padded out to a square with transparency first. ICNS holds only
    square icons, and Pillow will happily stretch a 600x900 poster to fill one,
    so the padding is what keeps the aspect ratio.
    """
    with Image.open(source) as image:
        art = image.convert("RGBA")
        side = max(art.size)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(art, ((side - art.width) // 2, (side - art.height) // 2))
        canvas.save(destination, "ICNS")
