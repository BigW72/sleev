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


def _save_png(image: Image.Image, destination: Path) -> None:
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


def data_to_png(data: bytes, destination: Path) -> None:
    """Write freshly downloaded image *data* to *destination* as a PNG."""
    with Image.open(BytesIO(data)) as image:
        _save_png(image, destination)
